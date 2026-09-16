from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from gateway.features.voice.domain.errors import (
    InvalidVoiceSessionError,
    VoiceSessionClosedError,
    VoiceTurnAlreadyActiveError,
    VoiceTurnNotFoundError,
)
from gateway.features.voice.domain.values import (
    Activation,
    AudioFormat,
    VoiceSessionStatus,
)
from gateway.features.voice.domain.voice_turn import VoiceTurn
from gateway.shared import Aggregate


class VoiceSession(Aggregate):
    def __init__(
        self,
        session_id: UUID,
        room: str,
        input_format: AudioFormat,
        output_format: AudioFormat,
        turns: Sequence[VoiceTurn] = (),
        status: VoiceSessionStatus = VoiceSessionStatus.OPEN,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
        last_sequence: int = 0,
        closed_at: datetime | None = None,
        close_reason: str | None = None,
    ) -> None:
        if not room.strip():
            raise InvalidVoiceSessionError("Voice room must not be empty")
        super().__init__(id=id, created_at=created_at)
        self._session_id = session_id
        self._room = room
        self._input_format = input_format
        self._output_format = output_format
        self._turns = list(turns)
        self._status = status
        self._last_sequence = last_sequence
        self._closed_at = closed_at
        self._close_reason = close_reason

    @property
    def session_id(self) -> UUID:
        return self._session_id

    @property
    def room(self) -> str:
        return self._room

    @property
    def input_format(self) -> AudioFormat:
        return self._input_format

    @property
    def output_format(self) -> AudioFormat:
        return self._output_format

    @property
    def turns(self) -> tuple[VoiceTurn, ...]:
        return tuple(self._turns)

    @property
    def status(self) -> VoiceSessionStatus:
        return self._status

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    @property
    def closed_at(self) -> datetime | None:
        return self._closed_at

    @property
    def close_reason(self) -> str | None:
        return self._close_reason

    @property
    def active_turn(self) -> VoiceTurn | None:
        return next(
            (turn for turn in reversed(self._turns) if not turn.status.terminal), None
        )

    def start_turn(self, activation: Activation) -> VoiceTurn:
        self._require_open()
        if self.active_turn is not None:
            raise VoiceTurnAlreadyActiveError(
                f"Voice session {self.id} already has an active turn"
            )
        turn = VoiceTurn(len(self._turns) + 1, activation)
        self._turns.append(turn)
        return turn

    def start_proactive_turn(self) -> VoiceTurn:
        self._require_open()
        if self.active_turn is not None:
            raise VoiceTurnAlreadyActiveError(
                f"Voice session {self.id} already has an active turn"
            )
        turn = VoiceTurn.proactive(len(self._turns) + 1)
        self._turns.append(turn)
        return turn

    def get_turn(self, turn_id: UUID) -> VoiceTurn:
        for turn in self._turns:
            if turn.id == turn_id:
                return turn
        raise VoiceTurnNotFoundError(turn_id)

    def next_sequence(self) -> int:
        self._last_sequence += 1
        return self._last_sequence

    def close(self, reason: str = "client", now: datetime | None = None) -> None:
        if self.status is VoiceSessionStatus.CLOSED:
            return
        timestamp = now or datetime.now(UTC)
        if (turn := self.active_turn) is not None:
            turn.cancel(timestamp)
        self._status = VoiceSessionStatus.CLOSED
        self._closed_at = timestamp
        self._close_reason = reason

    def _require_open(self) -> None:
        if self.status is VoiceSessionStatus.CLOSED:
            raise VoiceSessionClosedError(f"Voice session {self.id} is closed")
