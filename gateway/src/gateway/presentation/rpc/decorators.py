import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from types import FunctionType
from typing import Any

from pydantic import BaseModel

_METHOD_METADATA_KEY = "__cara_rpc_method__"
_EVENT_METADATA_KEY = "__cara_rpc_event__"


class RpcHandler:
    """Base for classes whose methods are exposed through `@rpc.method`."""


@dataclass(frozen=True, slots=True)
class RpcMethodMetadata:
    name: str
    summary: str | None
    errors: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RpcEventMetadata:
    name: str


@dataclass(frozen=True, slots=True)
class DecoratedRpcMethod:
    attribute_name: str
    function: FunctionType
    metadata: RpcMethodMetadata


def method[HandlerT: Callable[..., Any]](
    name: str,
    *,
    summary: str | None = None,
    errors: tuple[int, ...] = (),
) -> Callable[[HandlerT], HandlerT]:
    def decorate(handler: HandlerT) -> HandlerT:
        if _METHOD_METADATA_KEY in handler.__dict__:
            raise ValueError(f"RPC handler is already decorated: {handler.__name__}")
        setattr(
            handler,
            _METHOD_METADATA_KEY,
            RpcMethodMetadata(
                name=name,
                summary=summary or _docstring_summary(handler),
                errors=errors,
            ),
        )
        return handler

    return decorate


def event[EventT: type[BaseModel]](name: str) -> Callable[[EventT], EventT]:
    def decorate(message: EventT) -> EventT:
        if _EVENT_METADATA_KEY in message.__dict__:
            raise ValueError(f"RPC event is already decorated: {message.__name__}")
        schema = message.model_json_schema()
        event_type = schema.get("properties", {}).get("type", {}).get("const")
        if event_type != name:
            raise ValueError(
                f"RPC event {message.__name__} declares type {event_type!r}, "
                f"expected {name!r}"
            )
        setattr(message, _EVENT_METADATA_KEY, RpcEventMetadata(name=name))
        return message

    return decorate


def decorated_methods(
    handler: type[RpcHandler],
) -> Iterator[DecoratedRpcMethod]:
    for attribute_name, attribute in vars(handler).items():
        metadata = _method_metadata(attribute)
        if metadata is not None:
            yield DecoratedRpcMethod(attribute_name, attribute, metadata)


def event_metadata(message: type[BaseModel]) -> RpcEventMetadata | None:
    metadata = message.__dict__.get(_EVENT_METADATA_KEY)
    if metadata is None:
        return None
    if not isinstance(metadata, RpcEventMetadata):
        raise TypeError(f"Invalid RPC event metadata on {message.__name__}")
    return metadata


def _method_metadata(attribute: object) -> RpcMethodMetadata | None:
    if not isinstance(attribute, FunctionType):
        return None
    metadata = attribute.__dict__.get(_METHOD_METADATA_KEY)
    if metadata is None:
        return None
    if not isinstance(metadata, RpcMethodMetadata):
        raise TypeError(f"Invalid RPC method metadata on {attribute.__name__}")
    return metadata


def _docstring_summary(handler: Callable[..., Any]) -> str | None:
    if handler.__doc__ is None:
        return None
    return inspect.cleandoc(handler.__doc__).splitlines()[0].strip() or None
