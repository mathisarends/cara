import secrets
from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Header, HTTPException, status
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from sandbox_manager.settings import SandboxManagerYamlSettings


class AuthSettings(SandboxManagerYamlSettings):
    model_config = SettingsConfigDict(
        yaml_config_section="sandbox",
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
