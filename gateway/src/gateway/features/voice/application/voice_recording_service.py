import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from gateway.features.voice.application.ports import AudioEncoder, VoiceRecordingStore
from gateway.features.voice.application.voice_session_service import VoiceSessionService
from gateway.features.voice.domain import (
    VoiceRecordingNotFoundError,
    VoiceSession,
    VoiceTurnStatus,
)

logger = logging.getLogger(__name__)


class VoiceRecordingService:
    """Buffers each turn's audio and saves it once the turn has ended, so a
    voice session's recording holds its turns back to back without the idle
    time between them."""

    def __init__(
        self,
        sessions: VoiceSessionService,
        encoder: AudioEncoder,
        store: VoiceRecordingStore,
    ) -> None:
        self._sessions = sessions
        self._encoder = encoder
        self._store = store
        self._turns: dict[UUID, _TurnAudio] = {}
        self._saves: set[asyncio.Task[None]] = set()

    def record_input(self, voice_turn_id: UUID, pcm: bytes) -> None:
        self._turns.setdefault(voice_turn_id, _TurnAudio()).input.extend(pcm)

    def record_output(self, voice_turn_id: UUID, pcm: bytes) -> None:
        self._turns.setdefault(voice_turn_id, _TurnAudio()).output.extend(pcm)

    def finish(self, voice_session: VoiceSession) -> None:
        for turn in voice_session.turns:
            if not turn.status.terminal:
                continue
            audio = self._turns.pop(turn.id, None)
            # A discarded turn heard nothing worth keeping.
            if audio is None or turn.status is VoiceTurnStatus.DISCARDED:
                continue
            save = asyncio.create_task(self._save(voice_session, turn.index, audio))
            self._saves.add(save)
            save.add_done_callback(self._saves.discard)

    async def get(self, voice_session_id: UUID) -> bytes:
        await self._sessions.get(voice_session_id)
        recording = await self._store.load(voice_session_id)
        if recording is None:
            raise VoiceRecordingNotFoundError(voice_session_id)
        return recording

    async def close(self) -> None:
        if self._saves:
            await asyncio.gather(*self._saves, return_exceptions=True)

    async def _save(
        self,
        voice_session: VoiceSession,
        voice_turn_index: int,
        audio: "_TurnAudio",
    ) -> None:
        try:
            encoded = bytearray()
            if audio.input:
                encoded += await self._encoder.encode(
                    bytes(audio.input),
                    voice_session.input_format.sample_rate,
                )
            if audio.output:
                encoded += await self._encoder.encode(
                    bytes(audio.output),
                    voice_session.output_format.sample_rate,
                )
            if encoded:
                await self._store.save_turn(
                    voice_session.id,
                    voice_turn_index,
                    bytes(encoded),
                )
        except Exception:
            logger.exception(
                "Could not save turn %d of voice session %s",
                voice_turn_index,
                voice_session.id,
            )


@dataclass(slots=True)
class _TurnAudio:
    input: bytearray = field(default_factory=bytearray)
    output: bytearray = field(default_factory=bytearray)
