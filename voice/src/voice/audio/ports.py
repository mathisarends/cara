from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class AudioPlayback(ABC):
    @abstractmethod
    async def play(self, audio: bytes) -> None: ...


class AudioInput(ABC):
    @property
    @abstractmethod
    def sample_rate(self) -> int: ...

    @property
    @abstractmethod
    def channels(self) -> int: ...

    @property
    @abstractmethod
    def frames_per_chunk(self) -> int: ...

    @property
    @abstractmethod
    def is_active(self) -> bool: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def stream_chunks(self) -> AsyncIterator[bytes]: ...


class AudioOutput(ABC):
    @property
    @abstractmethod
    def is_playing(self) -> bool: ...

    @abstractmethod
    async def start(self, *, sample_rate: int, channels: int) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def play_chunk(self, chunk: bytes) -> None: ...

    async def finish_response(self) -> None:
        return None

    @abstractmethod
    async def clear_buffer(self) -> None: ...
