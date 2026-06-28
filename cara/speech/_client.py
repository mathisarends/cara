from typing import Any


def resolve_openai_client(client: Any | None = None) -> Any:
    if client is not None:
        return client

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("Install the 'openai' package to use Cara speech wrappers.") from exc

    return AsyncOpenAI()
