from typing import Any


def resolve_openai_client(client: Any | None = None) -> Any:
    if client is not None:
        return client

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("Install the 'openai' package to use Cara speech wrappers.") from exc

    from cara.settings import get_settings

    api_key = get_settings().openai_api_key
    if api_key is None:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your environment or to the project's .env file."
        )

    return AsyncOpenAI(api_key=api_key.get_secret_value())
