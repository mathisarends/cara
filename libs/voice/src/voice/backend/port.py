from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from voice.audio.models import AudioFormat, AudioFrame
from voice.backend.models import (
    BackendAudio,
    BackendConnectionOptions,
    BackendEvent,
    BackendSessionState,
    StartedTurn,
    StartTurn,
    TurnRef,
)


class VoiceBackend(ABC):
    """A remote voice session that transcribes, answers and synthesizes turns."""

    @property
    @abstractmethod
    def input_format(self) -> AudioFormat: ...

    @property
    @abstractmethod
    def output_format(self) -> AudioFormat: ...

    @property
    @abstractmethod
    def initial_state(self) -> BackendSessionState: ...

    @abstractmethod
    def events(self) -> AsyncIterator[BackendEvent]:
        """Yield lifecycle events until the session closes.

        The stream ends after yielding :class:`SessionClosed`; ending without
        it means the connection was lost.
        """

    @abstractmethod
    def output_audio(self) -> AsyncIterator[BackendAudio]:
        """Yield assistant audio in :attr:`output_format`.

        The first item of a turn starts its response, so audio never arrives
        for a response that has not started.
        """

    @abstractmethod
    async def start_turn(self, request: StartTurn) -> StartedTurn:
        """Start a turn, raising ``TurnAlreadyActiveError`` if one is active."""

    @abstractmethod
    async def send_input(self, turn: TurnRef, frame: AudioFrame) -> None: ...

    @abstractmethod
    async def end_input(self, turn: TurnRef, next_sequence: int) -> None: ...

    @abstractmethod
    async def interrupt(self, turn: TurnRef, sequence: int | None) -> None:
        """Stop the turn; ``sequence`` marks where the user took the floor."""

    @abstractmethod
    async def playback_completed(self, turn: TurnRef) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class VoiceBackendConnector(ABC):
    @abstractmethod
    async def connect(self, options: BackendConnectionOptions) -> VoiceBackend: ...
