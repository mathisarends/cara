from abc import ABC, abstractmethod


class LifecycleListener(ABC):
    """Abstract base for all assistant lifecycle listeners."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize and connect the listener."""

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect and release all resources."""


class ListenerRegistry:
    def __init__(self) -> None:
        self._listeners: list[LifecycleListener] = []

    def register(self, listener: LifecycleListener) -> None:
        self._listeners.append(listener)

    async def start(self) -> None:
        for listener in self._listeners:
            await listener.start()

    async def stop(self) -> None:
        for listener in reversed(self._listeners):
            await listener.stop()
