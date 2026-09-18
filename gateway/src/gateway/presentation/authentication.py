import secrets
from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_UNAUTHORIZED = "Unauthorized"
_BEARER = HTTPBearer(scheme_name="GatewayToken", auto_error=False)


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
        self._token = settings.token.get_secret_value().encode()

    def accepts_authorization(self, authorization: str) -> bool:
        scheme, separator, credential = authorization.partition(" ")
        return (
            separator == " " and scheme.lower() == "bearer" and self.accepts(credential)
        )

    def accepts(self, credential: str) -> bool:
        return secrets.compare_digest(credential.encode(), self._token)


# Declared after GatewayAuthenticator: dishka resolves the annotation on decoration.
@inject
async def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)],
    authenticator: FromDishka[GatewayAuthenticator],
) -> None:
    if credentials is None or not authenticator.accepts(credentials.credentials):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
