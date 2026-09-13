from collections.abc import Iterator
from unittest.mock import Mock

import pytest


class _Stream:
    def __init__(self, *reads: bytes | Exception, active: bool = True) -> None:
        self._reads = iter(reads)
        self._active = active
        self.stop_stream = Mock()
        self.close = Mock()

    def read(self, frames: int, *, exception_on_overflow: bool) -> bytes:
        result = next(self._reads)
        if isinstance(result, Exception):
            raise result
        return result

    def is_active(self) -> bool:
        return self._active


class _Session:
    def __init__(self) -> None:
        self.streams: list[_Stream] = []
        self.open_calls: list[dict[str, object]] = []
        self.closed = False

    def open_stream(self, **kwargs: object) -> _Stream:
        self.open_calls.append(kwargs)
        return self.streams.pop(0)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def stream_factory() -> Iterator[type[_Stream]]:
    yield _Stream


@pytest.fixture
def audio_session() -> _Session:
    return _Session()
