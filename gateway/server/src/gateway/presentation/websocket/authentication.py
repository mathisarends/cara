import secrets

from fastapi import WebSocket, WebSocketException, status
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewayAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_GATEWAY_",
        extra="ignore",
    )

    token: SecretStr = Field(min_length=32)


class GatewayAuthenticator:
    def __init__(self, settings: GatewayAuthSettings) -> None:
        self._token = settings.token.get_secret_value()

    def authenticate(self, socket: WebSocket) -> None:
        authorization = socket.headers.get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        if (
            separator != " "
            or scheme.lower() != "bearer"
            or not secrets.compare_digest(credential, self._token)
        ):
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Unauthorized",
            )
