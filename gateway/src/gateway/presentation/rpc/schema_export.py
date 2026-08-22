import argparse
import json
import re
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from gateway.features import gateway_protocol
from gateway.presentation.rpc.envelopes import RpcErrorCode, RpcFailure, RpcSuccess
from gateway.presentation.rpc.protocol import (
    GatewayProtocol,
    RpcMethodDefinition,
    RpcNotificationDefinition,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "gateway" / "schema"
_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_OPENRPC_VERSION = "1.3.2"


def render_gateway_schema(protocol: GatewayProtocol) -> dict[str, Any]:
    adapters = _adapters(protocol)
    schema_map, root = TypeAdapter.json_schemas(
        (
            (name, "validation", TypeAdapter(annotation))
            for name, annotation in adapters.items()
        ),
        title="Cara Gateway Protocol",
        description="JSON-RPC requests, responses, and notifications.",
    )
    refs = {name: schema_map[(name, "validation")] for name in adapters}
    definitions = root["$defs"]
    for method in protocol.methods:
        definitions[method.request_name] = _request_schema(method)
        refs[method.request_name] = {"$ref": f"#/$defs/{method.request_name}"}
    for notification in protocol.notifications:
        name = _notification_schema_name(notification.name)
        definitions[name] = _notification_schema(notification, name)
        refs[name] = {"$ref": f"#/$defs/{name}"}
    frame_names = [method.request_name for method in protocol.methods]
    frame_names.extend(("RpcSuccess", "RpcFailure"))
    frame_names.extend(
        _notification_schema_name(notification.name)
        for notification in protocol.notifications
    )
    return {
        "$schema": _JSON_SCHEMA_DIALECT,
        "$id": "https://cara.local/gateway.schema.json",
        "title": "Cara Gateway Protocol",
        "description": "JSON-RPC requests, responses, and notifications.",
        "oneOf": [refs[name] for name in frame_names],
        "$defs": definitions,
        "x-cara-protocol-version": protocol.version,
        "x-cara-methods": [
            {
                "name": method.name,
                "request": refs[method.request_name],
                "params": refs[_type_name(method.params)],
                "result": refs[_type_name(method.result)],
            }
            for method in protocol.methods
        ],
        "x-cara-notifications": [
            {
                "name": notification.name,
                "payload": refs[_type_name(notification.payload)],
                "message": refs[_notification_schema_name(notification.name)],
            }
            for notification in protocol.notifications
        ],
        "x-cara-events": [
            {
                "name": event.name,
                "payload": refs[_type_name(event.payload)],
            }
            for event in protocol.events
        ],
    }


def render_openrpc_schema(protocol: GatewayProtocol) -> dict[str, Any]:
    gateway_schema = render_gateway_schema(protocol)
    components = _rewrite_refs(gateway_schema["$defs"])
    return {
        "openrpc": _OPENRPC_VERSION,
        "info": {
            "title": "Cara Gateway",
            "version": f"{protocol.version}.0.0",
            "description": "Typed JSON-RPC API over the Cara Gateway WebSocket.",
        },
        "servers": [
            {
                "name": "local",
                "url": "ws://127.0.0.1:8000/v1/gateway",
            }
        ],
        "methods": [_openrpc_method(method, components) for method in protocol.methods],
        "components": {"schemas": components},
        "x-cara-protocol-version": protocol.version,
        "x-cara-notifications": [
            {
                "name": notification.name,
                "summary": notification.summary,
                "payload": {
                    "$ref": (f"#/components/schemas/{_type_name(notification.payload)}")
                },
                "message": {
                    "$ref": (
                        "#/components/schemas/"
                        f"{_notification_schema_name(notification.name)}"
                    )
                },
            }
            for notification in protocol.notifications
        ],
        "x-cara-events": [
            {
                "name": event.name,
                "payload": {"$ref": f"#/components/schemas/{event.payload.__name__}"},
            }
            for event in protocol.events
        ],
    }


def write_gateway_schemas(
    output_dir: Path,
    protocol: GatewayProtocol | None = None,
) -> tuple[Path, Path]:
    selected_protocol = protocol or gateway_protocol()
    output_dir.mkdir(parents=True, exist_ok=True)
    gateway_schema_path = output_dir / "gateway.schema.json"
    openrpc_schema_path = output_dir / "gateway.openrpc.json"
    _write_json(gateway_schema_path, render_gateway_schema(selected_protocol))
    _write_json(openrpc_schema_path, render_openrpc_schema(selected_protocol))
    return gateway_schema_path, openrpc_schema_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Cara Gateway JSON Schema and OpenRPC contract."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    for path in write_gateway_schemas(args.output_dir):
        print(f"Wrote {path}")


def _adapters(protocol: GatewayProtocol) -> dict[str, Any]:
    annotations: dict[str, Any] = {}
    for method in protocol.methods:
        _add_annotation(annotations, method.params)
        _add_annotation(annotations, method.result)
    for notification in protocol.notifications:
        _add_annotation(annotations, notification.payload)
    for event in protocol.events:
        _add_annotation(annotations, event.payload)
    for envelope in (RpcSuccess, RpcFailure):
        _add_annotation(annotations, envelope)
    return annotations


def _add_annotation(annotations: dict[str, Any], annotation: Any) -> None:
    name = _type_name(annotation)
    existing = annotations.get(name)
    if existing is not None and existing != annotation:
        raise ValueError(f"Duplicate protocol schema name: {name}")
    annotations[name] = annotation


def _type_name(annotation: Any) -> str:
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str):
        raise TypeError(f"Protocol type has no stable schema name: {annotation!r}")
    return name


def _openrpc_method(
    method: RpcMethodDefinition,
    components: dict[str, Any],
) -> dict[str, Any]:
    params_name = _type_name(method.params)
    params_schema = components[params_name]
    result_name = _type_name(method.result)
    result_schema = (
        {"$ref": f"#/components/schemas/{result_name}"}
        if result_name in components
        else _rewrite_refs(TypeAdapter(method.result).json_schema())
    )
    required = set(params_schema.get("required", ()))
    document: dict[str, Any] = {
        "name": method.name,
        **({"summary": method.summary} if method.summary is not None else {}),
        "paramStructure": "by-name",
        "params": [
            {
                "name": name,
                "required": name in required,
                "schema": schema,
            }
            for name, schema in params_schema.get("properties", {}).items()
        ],
        "result": {
            "name": "result",
            "schema": result_schema,
        },
        "x-cara-request-schema": {
            "$ref": f"#/components/schemas/{method.request_name}"
        },
        "x-cara-params-schema": {"$ref": f"#/components/schemas/{params_name}"},
    }
    if method.errors:
        document["errors"] = [
            {
                "code": int(code),
                "message": _error_message(code),
            }
            for code in method.errors
        ]
    return document


def _request_schema(method: RpcMethodDefinition) -> dict[str, Any]:
    params_schema = method.params.model_json_schema()
    required = ["jsonrpc", "method"]
    if params_schema.get("required"):
        required.append("params")
    return {
        "additionalProperties": False,
        "type": "object",
        "title": method.request_name,
        "properties": {
            "jsonrpc": {"const": "2.0", "type": "string"},
            "id": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "integer"},
                    {"type": "null"},
                ],
                "default": None,
            },
            "method": {"const": method.name, "type": "string"},
            "params": {"$ref": f"#/$defs/{method.params.__name__}"},
        },
        "required": required,
    }


def _notification_schema(
    notification: RpcNotificationDefinition,
    schema_name: str,
) -> dict[str, Any]:
    return {
        "additionalProperties": False,
        "type": "object",
        "title": schema_name,
        "properties": {
            "jsonrpc": {"const": "2.0", "type": "string"},
            "method": {"const": notification.name, "type": "string"},
            "params": {"$ref": f"#/$defs/{_type_name(notification.payload)}"},
        },
        "required": ["jsonrpc", "method", "params"],
    }


def _notification_schema_name(name: str) -> str:
    parts = (part for part in re.split(r"[^a-zA-Z0-9]+", name) if part)
    return "".join(part.capitalize() for part in parts) + "Notification"


def _error_message(code: int) -> str:
    messages = {
        RpcErrorCode.INVALID_PARAMS: "Invalid params",
        RpcErrorCode.INTERNAL_ERROR: "Internal error",
        RpcErrorCode.RESOURCE_NOT_FOUND: "Resource not found",
        RpcErrorCode.TURN_ALREADY_RUNNING: "Turn already running",
    }
    return messages[RpcErrorCode(code)]


def _rewrite_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_refs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_refs(item) for item in value]
    if isinstance(value, str) and value.startswith("#/$defs/"):
        return value.replace("#/$defs/", "#/components/schemas/", 1)
    return value


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
