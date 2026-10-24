from collections.abc import AsyncGenerator

from dishka import Scope
from fastapi import Request
from starlette.requests import HTTPConnection


async def http_request_scope(connection: HTTPConnection) -> AsyncGenerator[None]:
    """Commit HTTP work before sending a successful response."""
    if connection.scope["type"] != "http":
        yield
        return

    middleware_container = connection.state.dishka_container
    request = await middleware_container.get(Request)
    request_context = {Request: request}
    async with connection.app.state.dishka_container(
        request_context, scope=Scope.REQUEST
    ) as request_container:
        connection.state.dishka_container = request_container
        try:
            yield
        finally:
            connection.state.dishka_container = middleware_container
