import secrets
from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Header, HTTPException, status
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_SANDBOX_",
        extra="ignore",
    )

    token: SecretStr


@inject
async def require_token(
    authorization: Annotated[str, Header()],
    settings: FromDishka[AuthSettings],
) -> None:
    expected = f"Bearer {settings.token.get_secret_value()}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
