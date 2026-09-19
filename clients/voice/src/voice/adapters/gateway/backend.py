import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from uuid import UUID

import httpx2

from gateway_rest_client import GatewayRestClient, VoiceSessionSnapshotResponse
from gateway_rpc_client import GatewayRpcClient, VoiceTurnAlreadyActiveError
from gateway_rpc_client.models import (
    VoiceConversationEnded,
    VoiceEventMessage,
    VoiceTranscriptPartial,
    VoiceTurnStarted,
)
from voice.adapters.gateway.framing import MediaFrameKind
from voice.adapters.gateway.mapper import (
    backend_event,
    gateway_activation,
    session_state,
    voice_audio_format,
)
from voice.adapters.gateway.media import MediaTransport
from voice.audio import AudioFormat, AudioFrame
from voice.backend import (
    BackendAudio,
    BackendAudioEnd,
    BackendAudioFrame,
    BackendEvent,
    BackendSessionState,
    SessionClosed,
    StartedTurn,
    StartTurn,
    TurnAlreadyActiveError,
    TurnRef,
    VoiceBackend,
)

logger = logging.getLogger(__name__)


class GatewayVoiceBackend(VoiceBackend):
    """A Gateway voice session, reached over REST, JSON-RPC and a media stream."""

    def __init__(
        self,
        *,
        rest: GatewayRestClient,
        rpc: GatewayRpcClient,
        media: MediaTransport,
        snapshot: VoiceSessionSnapshotResponse,
        http: httpx2.AsyncClient,
        resources: AsyncExitStack,
    ) -> None:
        self._rest = rest
        self._rpc = rpc
        self._media = media
        self._snapshot = snapshot
        self._initial_state = session_state(snapshot)
        self._last_sequence = snapshot.last_sequence
        self._turn_indexes: dict[UUID, int] = {}
        self._turn_ids: dict[int, UUID] = {}
        self._remember_turns(snapshot)
        self._http = http
        self._resources = resources
        self._closed = False

    @property
    def input_format(self) -> AudioFormat:
        return voice_audio_format(self._snapshot.voice_session.input_format)

    @property
    def output_format(self) -> AudioFormat:
        return voice_audio_format(self._snapshot.voice_session.output_format)

    @property
    def initial_state(self) -> BackendSessionState:
        return self._initial_state

    async def events(self) -> AsyncIterator[BackendEvent]:
        async for event in self._rpc.voice.event():
            if not self._accepts(event):
                continue
            match event:
                case VoiceConversationEnded():
                    await self._follow_conversation()
                case VoiceTurnStarted():
                    # Media frames of the turn can arrive right after this.
                    await self._turn_index(event.voice_turn_id)
            mapped = backend_event(event)
            if mapped is None:
                continue
            yield mapped
            if isinstance(mapped, SessionClosed):
                return

    async def output_audio(self) -> AsyncIterator[BackendAudio]:
        async for frame in self._media.frames():
            turn_id = await self._turn_at(frame.voice_turn_index)
            if turn_id is None:
                logger.debug(
                    "Dropping a media frame of unknown turn index %d",
                    frame.voice_turn_index,
                )
                continue
            turn = TurnRef(turn_id)
            if frame.kind is MediaFrameKind.OUTPUT_END:
                yield BackendAudioEnd(turn=turn)
            else:
                yield BackendAudioFrame(turn=turn, pcm=frame.payload)

    async def start_turn(self, request: StartTurn) -> StartedTurn:
        activation = gateway_activation(request.activation)
        try:
            result = await self._rpc.voice.turn.start(
                voice_session_id=self._id,
                activation=activation,
                pre_roll_sequence=request.pre_roll_sequence,
            )
        except VoiceTurnAlreadyActiveError as error:
            raise TurnAlreadyActiveError(str(error)) from error
        turn_index = await self._turn_index(result.voice_turn_id)
        logger.info(
            "Voice turn %s started at index %d (%s)",
            result.voice_turn_id,
            turn_index,
            activation,
        )
        return StartedTurn(turn=TurnRef(result.voice_turn_id))

    async def send_input(self, turn: TurnRef, frame: AudioFrame) -> None:
        turn_index = await self._turn_index(turn.id)
        await self._media.send_input(turn_index, frame.sequence, frame.pcm)

    async def end_input(self, turn: TurnRef, next_sequence: int) -> None:
        turn_index = await self._turn_index(turn.id)
        await self._media.end_input(turn_index, next_sequence)

    async def interrupt(self, turn: TurnRef, sequence: int | None) -> None:
        await self._rpc.voice.turn.interrupt(
            voice_turn_id=turn.id,
            input_sequence=sequence,
        )

    async def playback_completed(self, turn: TurnRef) -> None:
        await self._rpc.voice.turn.playback_completed(voice_turn_id=turn.id)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._rest.close_voice_session(self._id)
        finally:
            try:
                await self._rpc.subscription.unsubscribe(session_id=self._session_id)
            finally:
                try:
                    await self._resources.aclose()
                finally:
                    await self._http.aclose()

    @property
    def _id(self) -> UUID:
        return self._snapshot.voice_session.id

    @property
    def _session_id(self) -> UUID:
        return self._snapshot.voice_session.session_id

    def _accepts(self, event: VoiceEventMessage) -> bool:
        if event.voice_session_id != self._id:
            logger.debug(
                "Dropping %s: it belongs to voice session %s",
                event.type,
                event.voice_session_id,
            )
            return False
        if isinstance(event, VoiceTranscriptPartial):
            logger.debug("Received %s revision %d", event.type, event.revision)
            return True
        if event.sequence <= self._last_sequence:
            logger.info(
                "Dropping %s: sequence %d was already seen (watermark %d)",
                event.type,
                event.sequence,
                self._last_sequence,
            )
            return False
        self._last_sequence = event.sequence
        logger.info("Received %s sequence %d", event.type, event.sequence)
        return True

    async def _turn_index(self, turn_id: UUID) -> int:
        turn_index = self._turn_indexes.get(turn_id)
        if turn_index is None:
            await self._refresh_snapshot()
            turn_index = self._turn_indexes.get(turn_id)
        if turn_index is None:
            raise RuntimeError(f"Voice turn {turn_id} is missing from the snapshot")
        return turn_index

    async def _turn_at(self, turn_index: int) -> UUID | None:
        turn_id = self._turn_ids.get(turn_index)
        # Only a turn newer than every known one can be missing from a stale
        # snapshot; older unknown indexes would refresh on every frame.
        if turn_id is None and turn_index > max(self._turn_ids, default=-1):
            await self._refresh_snapshot()
            turn_id = self._turn_ids.get(turn_index)
        return turn_id

    async def _refresh_snapshot(self) -> None:
        # Only consumed events advance the watermark: a snapshot taken while
        # later events are already on their way to the subscriber would
        # otherwise make them look like history and drop them.
        self._snapshot = await self._rest.get_voice_session(self._id)
        self._remember_turns(self._snapshot)

    def _remember_turns(self, snapshot: VoiceSessionSnapshotResponse) -> None:
        for turn in snapshot.turns:
            self._turn_indexes[turn.id] = turn.index
            self._turn_ids[turn.index] = turn.id

    async def _follow_conversation(self) -> None:
        # The Gateway moves the voice session to a fresh conversation session
        # when a conversation ends; its events are routed by that session.
        ended_session_id = self._session_id
        await self._refresh_snapshot()
        if self._session_id == ended_session_id:
            return
        await self._rpc.subscription.subscribe(session_id=self._session_id)
        await self._rpc.subscription.unsubscribe(session_id=ended_session_id)
        logger.info(
            "Voice session %s moved from conversation session %s to %s",
            self._id,
            ended_session_id,
            self._session_id,
        )
