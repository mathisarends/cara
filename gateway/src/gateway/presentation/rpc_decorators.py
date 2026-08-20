from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType
from typing import Any, TypeVar

from pydantic import BaseModel

_METHOD_METADATA_KEY = "__cara_rpc_method__"
_EVENT_METADATA_KEY = "__cara_rpc_event__"

Handler = TypeVar("Handler", bound=Callable[..., Any])
EventMessage = TypeVar("EventMessage", bound=type[BaseModel])


@dataclass(frozen=True, slots=True)
class RpcMethodMetadata:
    name: str
    summary: str
    errors: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RpcEventMetadata:
    name: str


def method(
    name: str,
    *,
    summary: str,
    errors: tuple[int, ...] = (),
) -> Callable[[Handler], Handler]:
    def decorate(handler: Handler) -> Handler:
        if _METHOD_METADATA_KEY in handler.__dict__:
            raise ValueError(f"RPC handler is already decorated: {handler.__name__}")
        setattr(
            handler,
            _METHOD_METADATA_KEY,
            RpcMethodMetadata(name=name, summary=summary, errors=errors),
        )
        return handler

    return decorate


def event(name: str) -> Callable[[EventMessage], EventMessage]:
    def decorate(message: EventMessage) -> EventMessage:
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


def method_metadata(handler: object) -> RpcMethodMetadata | None:
    if not isinstance(handler, FunctionType):
        return None
    metadata = handler.__dict__.get(_METHOD_METADATA_KEY)
    if metadata is None:
        return None
    if not isinstance(metadata, RpcMethodMetadata):
        raise TypeError(f"Invalid RPC method metadata on {handler.__name__}")
    return metadata


def event_metadata(message: type[BaseModel]) -> RpcEventMetadata | None:
    metadata = message.__dict__.get(_EVENT_METADATA_KEY)
    if metadata is None:
        return None
    if not isinstance(metadata, RpcEventMetadata):
        raise TypeError(f"Invalid RPC event metadata on {message.__name__}")
    return metadata
