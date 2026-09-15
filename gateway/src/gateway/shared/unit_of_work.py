from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager


class UnitOfWork[ServiceT](ABC):
    """Resolve one service within one short-lived transaction."""

    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[ServiceT]: ...
