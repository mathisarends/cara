"""Generate the typed layer of ``gateway_client`` from the OpenAPI spec.

Writes two modules:

* ``models.py`` — pydantic models for every schema in ``components.schemas``.
* ``operations.py`` — one namespace class per tag, one method per operation,
  wired to the hand-written ``Transport``.

Covers the subset of OpenAPI 3.1 the Cara Gateway emits and raises
``UnsupportedSchemaError`` on anything outside it, so an unhandled construct
surfaces as a failed generation instead of silently wrong code.

Two deliberate deviations from the spec:

* Field descriptions are dropped; the models are a wire contract, not docs.
* ``additionalProperties: false`` does not become ``extra="forbid"``; a client
  must keep parsing responses after the server adds a field.
"""

import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parent
_SPEC_PATH = _PACKAGE_ROOT / "openapi.json"
_OUTPUT_DIR = _PACKAGE_ROOT / "src" / "gateway_client"

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_SCALAR_TYPES = {
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "null": "None",
}
_STRING_FORMATS = {"uuid": "UUID", "date-time": "datetime"}
_CONSTRAINTS = {
    "minLength": "min_length",
    "maxLength": "max_length",
    "minItems": "min_length",
    "maxItems": "max_length",
    "minimum": "ge",
    "maximum": "le",
    "exclusiveMinimum": "gt",
    "exclusiveMaximum": "lt",
    "pattern": "pattern",
}
_STDLIB_IMPORTS = {
    "datetime": "from datetime import datetime",
    "StrEnum": "from enum import StrEnum",
    "UUID": "from uuid import UUID",
}
_TYPING_NAMES = ("Annotated", "Any", "Literal")
_PYDANTIC_NAMES = ("BaseModel", "Field", "TypeAdapter")


class UnsupportedSchemaError(Exception):
    pass


def main() -> None:
    args = _parse_args()
    spec = _load_spec(args.url, args.spec)
    for filename, source in (
        ("models.py", render_models(spec)),
        ("operations.py", render_operations(spec)),
    ):
        path = args.output_dir / filename
        path.write_text(source, encoding="utf-8")
        _format(path)
        print(f"Wrote {path}")


def render_models(spec: dict[str, Any]) -> str:
    schemas = spec["components"]["schemas"]
    names = _public_names(schemas)
    blocks: list[_Block] = []
    union_members: set[str] = set()

    for raw_name, schema in schemas.items():
        if "oneOf" not in schema:
            continue
        blocks.extend(_render_union(names[raw_name], schema, schemas, names))
        union_members.update(_ref_name(member) for member in schema["oneOf"])

    for raw_name, schema in schemas.items():
        if "oneOf" in schema or raw_name in union_members:
            continue
        blocks.append(_render_model(names[raw_name], "BaseModel", schema, names))

    body = "\n\n\n".join(block.source for block in _ordered(blocks))
    return _module(_header(spec, "wire models"), _model_imports(body), body)


def render_operations(spec: dict[str, Any]) -> str:
    names = _public_names(spec["components"]["schemas"])
    namespaces: dict[str, list[_Operation]] = {}
    for path, item in spec["paths"].items():
        for method in _HTTP_METHODS:
            operation = item.get(method)
            if operation is None:
                continue
            tag = _tag(operation, path)
            namespaces.setdefault(tag, []).append(
                _operation(method, path, operation, names)
            )

    blocks = [
        _render_namespace(tag, operations) for tag, operations in namespaces.items()
    ]
    blocks.append(_render_api(namespaces))
    body = "\n\n\n".join(blocks)
    return _module(_header(spec, "operations"), _operation_imports(body, names), body)


class _Block:
    def __init__(self, name: str, source: str, deps: set[str]) -> None:
        self.name = name
        self.source = source
        self.deps = deps


class _Operation:
    def __init__(
        self,
        name: str,
        method: str,
        path: str,
        parameters: list[tuple[str, str]],
        body: str | None,
        returns: str,
        parse: str | None,
    ) -> None:
        self.name = name
        self.method = method
        self.path = path
        self.parameters = parameters
        self.body = body
        self.returns = returns
        self.parse = parse


def _render_namespace(tag: str, operations: list[_Operation]) -> str:
    lines = [
        f"class {_namespace_class(tag)}:",
        "    def __init__(self, transport: Transport) -> None:",
        "        self._transport = transport",
    ]
    for operation in operations:
        lines.append("")
        lines.extend(_render_operation(operation))
    return "\n".join(lines)


def _render_operation(operation: _Operation) -> list[str]:
    parameters = "".join(
        f", {name}: {annotation}" for name, annotation in operation.parameters
    )
    if operation.body is not None:
        parameters += f", body: {operation.body}"

    call = [f'"{operation.method.upper()}"', _path_expression(operation)]
    if operation.body is not None:
        call.append('json=body.model_dump(mode="json")')
    request = f"await self._transport.request({', '.join(call)})"

    signature = f"    async def {operation.name}(self{parameters})"
    lines = [f"{signature} -> {operation.returns}:"]
    if operation.parse is None:
        lines.append(f"        {request}")
    else:
        lines.append(f"        response = {request}")
        lines.append(f"        return {operation.parse}")
    return lines


def _render_api(namespaces: dict[str, list[_Operation]]) -> str:
    lines = [
        "class GatewayApi:",
        "    def __init__(self, transport: Transport) -> None:",
    ]
    for tag in namespaces:
        lines.append(f"        self.{_namespace_attribute(tag)} = ")
        lines[-1] += f"{_namespace_class(tag)}(transport)"
    return "\n".join(lines)


def _operation(
    method: str,
    path: str,
    operation: dict[str, Any],
    names: dict[str, str],
) -> _Operation:
    returns, parse = _response(operation, names)
    return _Operation(
        name=operation["operationId"],
        method=method,
        path=path,
        parameters=_parameters(operation, names),
        body=_request_body(operation, names),
        returns=returns,
        parse=parse,
    )


def _parameters(
    operation: dict[str, Any],
    names: dict[str, str],
) -> list[tuple[str, str]]:
    parameters = []
    for parameter in operation.get("parameters", ()):
        if parameter["in"] != "path":
            raise UnsupportedSchemaError(
                f"Only path parameters are supported, got {parameter['in']!r} "
                f"parameter {parameter['name']!r}"
            )
        parameters.append((parameter["name"], _annotation(parameter["schema"], names)))
    return parameters


def _request_body(operation: dict[str, Any], names: dict[str, str]) -> str | None:
    body = operation.get("requestBody")
    if body is None:
        return None
    schema = _json_schema(body["content"])
    if "$ref" not in schema:
        raise UnsupportedSchemaError(f"Inline request body is not supported: {schema}")
    return names[_ref_name(schema)]


def _response(
    operation: dict[str, Any],
    names: dict[str, str],
) -> tuple[str, str | None]:
    successes = sorted(code for code in operation["responses"] if code.startswith("2"))
    if not successes:
        raise UnsupportedSchemaError(f"No success response: {operation['operationId']}")
    content = operation["responses"][successes[0]].get("content")
    if content is None:
        return "None", None
    schema = _json_schema(content)
    if "$ref" in schema:
        model = names[_ref_name(schema)]
        return model, f"{model}.model_validate_json(response.content)"
    return _annotation(schema, names), "response.json()"


def _json_schema(content: dict[str, Any]) -> dict[str, Any]:
    if "application/json" not in content:
        raise UnsupportedSchemaError(f"Only JSON payloads are supported: {content}")
    return content["application/json"]["schema"]


def _path_expression(operation: _Operation) -> str:
    prefix = "f" if operation.parameters else ""
    return f'{prefix}"{operation.path}"'


def _tag(operation: dict[str, Any], path: str) -> str:
    tags = operation.get("tags")
    if not tags:
        raise UnsupportedSchemaError(f"Operation without tag: {path}")
    return tags[0]


def _namespace_class(tag: str) -> str:
    parts = re.split(r"\W|_", tag)
    return "".join(part.capitalize() for part in parts if part) + "Operations"


def _namespace_attribute(tag: str) -> str:
    return re.sub(r"\W", "_", tag).lower()


def _render_union(
    name: str,
    schema: dict[str, Any],
    schemas: dict[str, Any],
    names: dict[str, str],
) -> list[_Block]:
    discriminator = _discriminator(schema)
    raw_names = [_ref_name(member) for member in schema["oneOf"]]
    members = [schemas[raw_name] for raw_name in raw_names]
    stem = name.removesuffix("Message")
    enum_name = f"{stem}{discriminator.title()}"
    base_name = f"{stem}Base"

    common = _common_properties(members, discriminator)
    blocks = [
        _render_enum(enum_name, members, discriminator),
        _render_model(base_name, "BaseModel", _subset(members[0], common), names),
    ]
    member_names = [names[raw_name] for raw_name in raw_names]
    for member_name, member in zip(member_names, members, strict=True):
        block = _render_model(
            member_name,
            base_name,
            _subset(member, _remaining(member, common)),
            names,
            overrides={
                discriminator: (
                    f"Literal[{enum_name}.{_enum_member(member, discriminator)}]"
                )
            },
        )
        block.deps.add(enum_name)
        blocks.append(block)

    alias = " | ".join(member_names)
    adapter = f"{_snake_case(stem)}_adapter"
    blocks.append(
        _Block(
            name,
            f"type {name} = Annotated[\n"
            f"    {alias},\n"
            f'    Field(discriminator="{discriminator}"),\n'
            f"]\n\n"
            f"{adapter}: TypeAdapter[{name}] = TypeAdapter({name})",
            set(member_names),
        )
    )
    return blocks


def _render_enum(
    name: str,
    members: list[dict[str, Any]],
    discriminator: str,
) -> _Block:
    lines = [f"class {name}(StrEnum):"]
    for member in members:
        value = member["properties"][discriminator]["const"]
        lines.append(f'    {_enum_member(member, discriminator)} = "{value}"')
    return _Block(name, "\n".join(lines), set())


def _render_model(
    name: str,
    base: str,
    schema: dict[str, Any],
    names: dict[str, str],
    overrides: dict[str, str] | None = None,
) -> _Block:
    properties = schema.get("properties", {})
    required = set(schema.get("required", ()))
    deps = {base} if base != "BaseModel" else set()
    lines = [f"class {name}({base}):"]

    for field, field_schema in properties.items():
        annotation = (overrides or {}).get(field) or _annotation(field_schema, names)
        default = _default(field_schema, field in required, annotation)
        if default is None:
            lines.append(f"    {field}: {annotation}")
        else:
            annotation = _optional(annotation, field_schema, field in required)
            lines.append(f"    {field}: {annotation} = {default}")
        deps.update(_dependencies(field_schema, names))

    if not properties:
        lines.append("    pass")
    return _Block(name, "\n".join(lines), deps)


def _annotation(schema: dict[str, Any], names: dict[str, str]) -> str:
    if "$ref" in schema:
        return names[_ref_name(schema)]
    if "const" in schema:
        return f"Literal[{schema['const']!r}]"
    if "enum" in schema:
        return f"Literal[{', '.join(repr(value) for value in schema['enum'])}]"
    if "anyOf" in schema:
        return " | ".join(
            dict.fromkeys(_annotation(option, names) for option in schema["anyOf"])
        )
    if "oneOf" in schema:
        raise UnsupportedSchemaError(f"Inline oneOf is not supported: {schema}")

    schema_type = schema.get("type")
    if schema_type is None:
        return "Any"
    if isinstance(schema_type, list):
        return " | ".join(
            _annotation({**schema, "type": option}, names) for option in schema_type
        )
    if schema_type == "string":
        return _STRING_FORMATS.get(schema.get("format", ""), "str")
    if schema_type in _SCALAR_TYPES:
        return _SCALAR_TYPES[schema_type]
    if schema_type == "array":
        return f"list[{_annotation(schema.get('items', {}), names)}]"
    if schema_type == "object":
        return _mapping_annotation(schema, names)
    raise UnsupportedSchemaError(f"Unknown schema type: {schema_type!r}")


def _mapping_annotation(schema: dict[str, Any], names: dict[str, str]) -> str:
    if schema.get("properties"):
        raise UnsupportedSchemaError(
            "Inline object schemas are not supported; extract them into "
            f"components.schemas: {schema}"
        )
    additional = schema.get("additionalProperties", True)
    value = "Any" if additional is True else _annotation(additional, names)
    return f"dict[str, {value}]"


def _default(schema: dict[str, Any], required: bool, annotation: str) -> str | None:
    constraints = _constraints(schema)
    if required:
        return _field_call(constraints, None) if constraints else None
    if "default" in schema:
        return _field_call(constraints, repr(schema["default"]))
    factory = _container_factory(schema, annotation)
    if factory is not None:
        return _field_call({**constraints, "default_factory": factory}, None)
    return _field_call(constraints, "None")


def _optional(annotation: str, schema: dict[str, Any], required: bool) -> str:
    if required or annotation == "Any" or "None" in annotation.split(" | "):
        return annotation
    if _container_factory(schema, annotation) is not None or "default" in schema:
        return annotation
    return f"{annotation} | None"


def _container_factory(schema: dict[str, Any], annotation: str) -> str | None:
    if annotation.startswith("dict[") or schema.get("type") == "object":
        return "dict"
    if annotation.startswith("list[") or schema.get("type") == "array":
        return "list"
    return None


def _field_call(kwargs: dict[str, Any], default: str | None) -> str:
    if not kwargs and default is not None:
        return default
    rendered = [f"{key}={value}" for key, value in kwargs.items()]
    if default is not None:
        rendered.insert(0, f"default={default}")
    return f"Field({', '.join(rendered)})"


def _constraints(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        _CONSTRAINTS[key]: repr(value)
        for key, value in schema.items()
        if key in _CONSTRAINTS
    }


def _dependencies(schema: Any, names: dict[str, str]) -> set[str]:
    if isinstance(schema, dict):
        if "$ref" in schema:
            return {names[_ref_name(schema)]}
        return set().union(
            *(_dependencies(value, names) for value in schema.values()), set()
        )
    if isinstance(schema, list):
        return set().union(*(_dependencies(item, names) for item in schema), set())
    return set()


def _common_properties(members: list[dict[str, Any]], discriminator: str) -> set[str]:
    first, *rest = members
    return {
        field
        for field, schema in first["properties"].items()
        if field != discriminator
        and all(other["properties"].get(field) == schema for other in rest)
        and all(
            (field in other.get("required", ())) == (field in first.get("required", ()))
            for other in rest
        )
    }


def _remaining(member: dict[str, Any], common: set[str]) -> set[str]:
    return set(member["properties"]) - common


def _subset(schema: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    return {
        "properties": {
            field: field_schema
            for field, field_schema in schema["properties"].items()
            if field in fields
        },
        "required": [field for field in schema.get("required", ()) if field in fields],
    }


def _discriminator(schema: dict[str, Any]) -> str:
    discriminator = schema.get("discriminator")
    if discriminator is None:
        raise UnsupportedSchemaError(f"Union without discriminator: {schema}")
    return discriminator["propertyName"]


def _enum_member(member: dict[str, Any], discriminator: str) -> str:
    return re.sub(r"\W", "_", member["properties"][discriminator]["const"]).upper()


def _ordered(blocks: list[_Block]) -> list[_Block]:
    pending = list(blocks)
    emitted: set[str] = set()
    ordered: list[_Block] = []
    while pending:
        ready = [block for block in pending if block.deps <= emitted | {block.name}]
        if not ready:
            unresolved = ", ".join(block.name for block in pending)
            raise UnsupportedSchemaError(f"Circular or missing refs: {unresolved}")
        ordered.extend(ready)
        emitted.update(block.name for block in ready)
        ready_names = {block.name for block in ready}
        pending = [block for block in pending if block.name not in ready_names]
    return ordered


def _public_names(schemas: dict[str, Any]) -> dict[str, str]:
    return {raw_name: raw_name.lstrip("_") for raw_name in schemas}


def _ref_name(schema: dict[str, Any]) -> str:
    return schema["$ref"].rsplit("/", 1)[-1]


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _module(header: str, imports: str, body: str) -> str:
    return f"{header}\n\n{imports}\n\n\n{body}\n"


def _header(spec: dict[str, Any], subject: str) -> str:
    info = spec["info"]
    return (
        f'"""Generated {subject} for the {info["title"]}, '
        f"version {info['version']}.\n\n"
        "Generated by gateway_client/scripts/generate_client.py.\n"
        'Do not edit by hand; refresh openapi.json and re-run the generator.\n"""'
    )


def _model_imports(body: str) -> str:
    stdlib = [
        statement for name, statement in _STDLIB_IMPORTS.items() if _uses(body, name)
    ] + _from_import("typing", _TYPING_NAMES, body)
    pydantic = _from_import("pydantic", _PYDANTIC_NAMES, body)
    return "\n".join([*sorted(stdlib), "", *pydantic])


def _operation_imports(body: str, names: dict[str, str]) -> str:
    stdlib = _from_import("uuid", ("UUID",), body) + _from_import(
        "typing", _TYPING_NAMES, body
    )
    models = sorted(name for name in names.values() if _uses(body, name))
    return "\n".join(
        [
            *sorted(stdlib),
            "",
            f"from gateway_client.models import {', '.join(models)}",
            "from gateway_client.transport import Transport",
        ]
    )


def _from_import(module: str, candidates: tuple[str, ...], body: str) -> list[str]:
    used = [name for name in candidates if _uses(body, name)]
    return [f"from {module} import {', '.join(used)}"] if used else []


def _uses(body: str, name: str) -> bool:
    return re.search(rf"\b{name}\b", body) is not None


def _load_spec(url: str | None, spec_path: Path) -> dict[str, Any]:
    if url is None:
        return json.loads(spec_path.read_text(encoding="utf-8"))
    with urllib.request.urlopen(f"{url.rstrip('/')}/openapi.json", timeout=10) as body:
        spec = json.loads(body.read())
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Refreshed {spec_path} from {url}")
    return spec


def _format(path: Path) -> None:
    for command in (["ruff", "format"], ["ruff", "check", "--fix"]):
        subprocess.run(["uv", "run", *command, str(path)], cwd=_REPO_ROOT, check=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url",
        help="Base URL of a running gateway; refreshes openapi.json before generating.",
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=_SPEC_PATH,
        help=f"Spec file to read (default: {_SPEC_PATH.name}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_OUTPUT_DIR,
        help="Package directory to write models.py and operations.py into.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
