import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from types import UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    TypeAliasType,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, ConfigDict, Field

from gateway.presentation.rpc_decorators import event_metadata, method_metadata


class RpcRequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    jsonrpc: Literal["2.0"]
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def expects_response(self) -> bool:
        return "id" in self.model_fields_set


@dataclass(frozen=True, slots=True)
class RpcMethodDefinition:
    name: str
    handler_name: str
    request_name: str
    params: type[BaseModel]
    result: Any
    summary: str
    errors: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class RpcNotificationDefinition:
    name: str
    payload: Any
    summary: str


@dataclass(frozen=True, slots=True)
class RpcEventDefinition:
    name: str
    payload: type[BaseModel]


@dataclass(frozen=True, slots=True)
class RpcFeatureDefinition:
    name: str
    handler: type[Any]
    methods: tuple[RpcMethodDefinition, ...] = ()
    notifications: tuple[RpcNotificationDefinition, ...] = ()
    events: tuple[RpcEventDefinition, ...] = ()


class RpcMethodNotFoundError(Exception):
    pass


class GatewayProtocol:
    def __init__(
        self,
        features: Iterable[RpcFeatureDefinition],
        *,
        version: int = 1,
    ) -> None:
        self._version = version
        self._features = tuple(features)
        self._methods = _unique_methods(self._features)
        self._notifications = _unique_notifications(self._features)
        self._events = _unique_events(self._features)

    @property
    def version(self) -> int:
        return self._version

    @property
    def features(self) -> tuple[RpcFeatureDefinition, ...]:
        return self._features

    @property
    def methods(self) -> tuple[RpcMethodDefinition, ...]:
        return tuple(self._methods.values())

    @property
    def notifications(self) -> tuple[RpcNotificationDefinition, ...]:
        return tuple(self._notifications.values())

    @property
    def events(self) -> tuple[RpcEventDefinition, ...]:
        return tuple(self._events.values())

    def method(self, name: str) -> RpcMethodDefinition:
        try:
            return self._methods[name]
        except KeyError as error:
            raise RpcMethodNotFoundError(name) from error


def rpc_feature(
    name: str,
    *,
    handler: type[Any],
    notifications: tuple[RpcNotificationDefinition, ...] = (),
) -> RpcFeatureDefinition:
    methods = tuple(
        _method_definition(handler_name, value)
        for handler_name, value in vars(handler).items()
        if method_metadata(value) is not None
    )
    events = tuple(
        event
        for notification in notifications
        for event in _event_definitions(notification.payload)
    )
    return RpcFeatureDefinition(
        name=name,
        handler=handler,
        methods=methods,
        notifications=notifications,
        events=events,
    )


def _method_definition(
    handler_name: str,
    handler: Any,
) -> RpcMethodDefinition:
    metadata = method_metadata(handler)
    if metadata is None:
        raise ValueError(f"RPC handler is not decorated: {handler_name}")
    signature = inspect.signature(handler)
    parameters = tuple(signature.parameters.values())
    if len(parameters) != 2 or parameters[0].name != "self":
        raise TypeError(
            f"RPC handler {handler.__qualname__} must accept only self and params"
        )
    hints = get_type_hints(handler)
    params = hints.get(parameters[1].name)
    result = hints.get("return")
    if not isinstance(params, type) or not issubclass(params, BaseModel):
        raise TypeError(
            f"RPC handler {handler.__qualname__} params must be a Pydantic model"
        )
    if result is None:
        raise TypeError(f"RPC handler {handler.__qualname__} needs a return annotation")
    if result is not type(None) and (
        not isinstance(result, type) or not issubclass(result, BaseModel)
    ):
        raise TypeError(
            f"RPC handler {handler.__qualname__} result must be a Pydantic model "
            "or None"
        )
    return RpcMethodDefinition(
        name=metadata.name,
        handler_name=handler_name,
        request_name=f"{_pascal_case(handler_name)}Request",
        params=params,
        result=result,
        summary=metadata.summary,
        errors=metadata.errors,
    )


def _event_definitions(annotation: Any) -> tuple[RpcEventDefinition, ...]:
    definitions: list[RpcEventDefinition] = []
    for message in _event_message_types(annotation):
        metadata = event_metadata(message)
        if metadata is None:
            raise ValueError(f"RPC event is not decorated: {message.__name__}")
        definitions.append(RpcEventDefinition(metadata.name, message))
    return tuple(definitions)


def _event_message_types(annotation: Any) -> tuple[type[BaseModel], ...]:
    value = (
        annotation.__value__ if isinstance(annotation, TypeAliasType) else annotation
    )
    if get_origin(value) is Annotated:
        value = get_args(value)[0]
    members = get_args(value) if get_origin(value) is UnionType else (value,)
    if not all(
        isinstance(member, type) and issubclass(member, BaseModel) for member in members
    ):
        raise TypeError("RPC notification payload must contain Pydantic event models")
    return members


def _unique_methods(
    features: tuple[RpcFeatureDefinition, ...],
) -> dict[str, RpcMethodDefinition]:
    methods: dict[str, RpcMethodDefinition] = {}
    for feature in features:
        for method in feature.methods:
            if method.name in methods:
                raise ValueError(f"Duplicate RPC method: {method.name}")
            methods[method.name] = method
    return methods


def _unique_notifications(
    features: tuple[RpcFeatureDefinition, ...],
) -> dict[str, RpcNotificationDefinition]:
    notifications: dict[str, RpcNotificationDefinition] = {}
    for feature in features:
        for notification in feature.notifications:
            if notification.name in notifications:
                raise ValueError(f"Duplicate RPC notification: {notification.name}")
            notifications[notification.name] = notification
    return notifications


def _unique_events(
    features: tuple[RpcFeatureDefinition, ...],
) -> dict[str, RpcEventDefinition]:
    events: dict[str, RpcEventDefinition] = {}
    for feature in features:
        for event in feature.events:
            if event.name in events:
                raise ValueError(f"Duplicate RPC event: {event.name}")
            events[event.name] = event
    return events


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))
