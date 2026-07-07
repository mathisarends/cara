import collections.abc
import inspect
import types
from collections.abc import Callable
from enum import Enum
from typing import Annotated, Any, ClassVar, Literal, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from cara.tools.di import _InjectMarker


def is_injectable(hint: Any) -> bool:
    if get_origin(hint) is not Annotated:
        return False
    return any(isinstance(metadata, _InjectMarker) for metadata in get_args(hint))


def _apply_field_constraints(prop: dict[str, Any], metadata: list[Any]) -> None:
    if prop.get("type") != "array":
        return

    for constraint in metadata:
        min_length = getattr(constraint, "min_length", None)
        if min_length is not None:
            prop["minItems"] = min_length

        max_length = getattr(constraint, "max_length", None)
        if max_length is not None:
            prop["maxItems"] = max_length


def _is_pydantic_model(model: Any) -> bool:
    return isinstance(model, type) and issubclass(model, BaseModel)


def _is_enum(model: Any) -> bool:
    return isinstance(model, type) and issubclass(model, Enum)


class ToolSchemaBuilder:
    _PRIMITIVE_TYPES: ClassVar[dict[type, str]] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    _COLLECTION_TYPES: ClassVar[tuple[type, ...]] = (
        collections.abc.Sequence,
        collections.abc.Iterable,
        collections.abc.Collection,
    )

    def __init__(
        self,
        function: Callable[..., Any],
        param_model: type[BaseModel] | None = None,
    ) -> None:
        self._function = function
        self._param_model = param_model

    def build(self) -> dict[str, Any]:
        if self._param_model is not None:
            return self._build_from_pydantic_model(self._param_model)

        signature = inspect.signature(self._function)
        hints = get_type_hints(self._function, include_extras=True)

        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []

        for param_name, param in signature.parameters.items():
            if param_name in ("self", "cls"):
                continue

            hint = hints.get(param_name, str)
            if is_injectable(hint):
                continue

            actual_type, description = self._extract_type_and_description(hint)
            properties[param_name] = self._to_json_property(actual_type, description)

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _extract_type_and_description(self, hint: Any) -> tuple[Any, str | None]:
        if get_origin(hint) is not Annotated:
            return hint, None
        args = get_args(hint)
        description = next((metadata for metadata in args[1:] if isinstance(metadata, str)), None)
        return args[0], description

    def _unwrap_optional(self, hint: Any) -> Any | None:
        origin = get_origin(hint)
        if origin is Union or isinstance(hint, types.UnionType):
            non_none = [arg for arg in get_args(hint) if arg is not type(None)]
            return non_none[0] if len(non_none) == 1 else None
        return None

    def _to_json_property(self, python_type: Any, description: str | None = None) -> dict[str, Any]:
        prop: dict[str, Any] = {}
        if description:
            prop["description"] = description

        unwrapped = self._unwrap_optional(python_type)
        if unwrapped is not None:
            return self._to_json_property(unwrapped, description)

        origin = get_origin(python_type)
        if origin is Literal:
            return {
                **prop,
                "type": "string",
                "enum": [str(value) for value in get_args(python_type)],
            }
        if origin is list or origin in self._COLLECTION_TYPES:
            args = get_args(python_type)
            item_type = args[0] if args else str
            return {**prop, "type": "array", "items": self._to_json_property(item_type)}
        if origin is dict:
            return {**prop, "type": "object"}

        if _is_pydantic_model(python_type):
            return self._build_model_property(python_type, description)

        if _is_enum(python_type):
            return {
                **prop,
                "type": "string",
                "enum": [member.value for member in python_type],
            }

        json_type = self._PRIMITIVE_TYPES.get(python_type, "string")
        return {**prop, "type": json_type}

    def _build_from_pydantic_model(self, model: type[BaseModel]) -> dict[str, Any]:
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []

        for field_name, field_info in model.model_fields.items():
            properties[field_name] = self._to_json_property(
                field_info.annotation,
                field_info.description,
            )
            _apply_field_constraints(properties[field_name], field_info.metadata)
            if not field_info.is_required() and field_info.default not in (
                None,
                PydanticUndefined,
            ):
                properties[field_name]["default"] = field_info.default
            if field_info.is_required():
                required.append(field_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _build_model_property(self, model: type[BaseModel], description: str | None) -> dict[str, Any]:
        schema = self._build_from_pydantic_model(model)
        if description:
            schema["description"] = description
        return schema
