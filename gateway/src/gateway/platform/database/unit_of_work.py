from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer, Scope

from gateway.shared.unit_of_work import UnitOfWork


class ScopedUnitOfWork[ServiceT](UnitOfWork[ServiceT]):
    """Resolve a service in a fresh request-scoped transaction."""

    def __init__(self, container: AsyncContainer, service: type[ServiceT]) -> None:
        self._container = container
        self._service = service

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[ServiceT]:
        async with self._container(scope=Scope.REQUEST) as scoped:
            service = await scoped.get(self._service)
            yield service
