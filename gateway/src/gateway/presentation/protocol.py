from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, TypeAdapter


@dataclass(frozen=True, slots=True)
class RpcMethodDefinition:
    name: str
    request: type[BaseModel]
    params: Any
    result: Any
    summary: str
    errors: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class RpcNotificationDefinition:
    name: str
    payload: Any
    summary: str


@dataclass(frozen=True, slots=True)
class RpcFeatureDefinition:
    name: str
    methods: tuple[RpcMethodDefinition, ...] = ()
    notifications: tuple[RpcNotificationDefinition, ...] = ()


class RpcMethodNotFoundError(Exception):
    pass


class RpcInvalidRequestError(Exception):
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
        for method in self._methods.values():
            _validate_request_model(method)

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

    def method(self, name: str) -> RpcMethodDefinition:
        try:
            return self._methods[name]
        except KeyError as error:
            raise RpcMethodNotFoundError(name) from error

    def parse_request(self, raw_request: object) -> BaseModel:
        if not isinstance(raw_request, dict):
            raise RpcInvalidRequestError from None
        method = raw_request.get("method")
        if not isinstance(method, str):
            raise RpcInvalidRequestError from None
        definition = self.method(method)
        return TypeAdapter(definition.request).validate_python(raw_request)


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


def _validate_request_model(method: RpcMethodDefinition) -> None:
    schema = method.request.model_json_schema()
    properties = schema.get("properties", {})
    method_schema = properties.get("method", {})
    if method_schema.get("const") != method.name:
        raise ValueError(
            f"RPC request {method.request.__name__} does not declare "
            f"method {method.name!r}"
        )
    params_annotation = method.request.model_fields["params"].annotation
    if params_annotation != method.params:
        raise ValueError(
            f"RPC request {method.request.__name__} params do not match "
            f"{_type_name(method.params)}"
        )


def _type_name(annotation: Any) -> str:
    return getattr(annotation, "__name__", repr(annotation))
