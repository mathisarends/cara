from abc import ABC, abstractmethod


class ReadinessCheck(ABC):
    @abstractmethod
    async def check(self) -> None:
        """Raise ``DependencyUnavailableError`` when the dependency is not usable."""
