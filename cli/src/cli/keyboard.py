import asyncio
import contextlib
import os
import select
import sys
import threading
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

_ESCAPE = "\x1b"
_INTERRUPT = "\x03"
_END_OF_TRANSMISSION = "\x04"
_ESCAPE_SEQUENCE_TIMEOUT = 0.05


class ControlKey(StrEnum):
    SUBMIT = "submit"
    BACKSPACE = "backspace"
    ESCAPE = "escape"
    QUIT = "quit"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Character:
    value: str


type KeyEvent = Character | ControlKey


class Keyboard:
    """Streams key events from stdin, in raw mode when stdin is a terminal.

    Without a terminal the reader falls back to whole lines, which still
    produces characters and SUBMIT — only ESCAPE can never arrive.
    """

    def __init__(self) -> None:
        self._source = _key_source()
        self._events: asyncio.Queue[KeyEvent | None] = asyncio.Queue()
        self._reader: threading.Thread | None = None

    @property
    def interactive(self) -> bool:
        return self._source.interactive

    async def __aenter__(self) -> Self:
        self._source.open()
        loop = asyncio.get_running_loop()
        self._reader = threading.Thread(
            target=self._read_forever,
            args=(loop,),
            name="cara-cli-keyboard",
            daemon=True,
        )
        self._reader.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        self._source.close()

    async def events(self) -> AsyncIterator[KeyEvent]:
        while (event := await self._events.get()) is not None:
            yield event

    def stop(self) -> None:
        self._events.put_nowait(None)

    def _read_forever(self, loop: asyncio.AbstractEventLoop) -> None:
        while (event := self._source.read()) is not None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._events.put_nowait, event)
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self.stop)


class _KeySource(ABC):
    interactive: bool

    @abstractmethod
    def open(self) -> None:
        """Put stdin into the mode this source reads from."""

    @abstractmethod
    def close(self) -> None:
        """Restore the mode stdin was in before open()."""

    @abstractmethod
    def read(self) -> KeyEvent | None:
        """Block until the next key; None once stdin is exhausted."""


class _LineKeySource(_KeySource):
    interactive = False

    def __init__(self) -> None:
        self._pending: list[KeyEvent] = []

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def read(self) -> KeyEvent | None:
        while not self._pending:
            line = sys.stdin.readline()
            if not line:
                return None
            self._pending = [Character(char) for char in line.rstrip("\r\n")]
            self._pending.append(ControlKey.SUBMIT)
        return self._pending.pop(0)


class _WindowsKeySource(_KeySource):
    interactive = True

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def read(self) -> KeyEvent | None:
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            msvcrt.getwch()
            return ControlKey.UNKNOWN
        return _key_event(char)


class _PosixKeySource(_KeySource):
    interactive = True

    def __init__(self) -> None:
        self._descriptor = sys.stdin.fileno()
        self._saved: list[Any] | None = None

    def open(self) -> None:
        import termios
        import tty

        self._saved = termios.tcgetattr(self._descriptor)
        tty.setraw(self._descriptor)

    def close(self) -> None:
        import termios

        if self._saved is None:
            return
        termios.tcsetattr(self._descriptor, termios.TCSADRAIN, self._saved)
        self._saved = None

    def read(self) -> KeyEvent | None:
        data = os.read(self._descriptor, 1)
        if not data:
            return None
        char = data.decode("utf-8", errors="replace")
        if char == _ESCAPE and self._sequence_follows():
            self._drain_sequence()
            return ControlKey.UNKNOWN
        return _key_event(char)

    def _sequence_follows(self) -> bool:
        ready, _, _ = select.select(
            [self._descriptor], [], [], _ESCAPE_SEQUENCE_TIMEOUT
        )
        return bool(ready)

    def _drain_sequence(self) -> None:
        while (data := os.read(self._descriptor, 1)) and not data.isalpha():
            if data in (b"~", b"$"):
                return


def _key_source() -> _KeySource:
    if not sys.stdin.isatty():
        return _LineKeySource()
    if sys.platform == "win32":
        return _WindowsKeySource()
    return _PosixKeySource()


def _key_event(char: str) -> KeyEvent:
    if char in ("\r", "\n"):
        return ControlKey.SUBMIT
    if char in ("\x7f", "\b"):
        return ControlKey.BACKSPACE
    if char == _ESCAPE:
        return ControlKey.ESCAPE
    if char in (_INTERRUPT, _END_OF_TRANSMISSION):
        return ControlKey.QUIT
    return Character(char) if char.isprintable() else ControlKey.UNKNOWN
