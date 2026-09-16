import logging
from collections.abc import AsyncIterator
from typing import Self
from uuid import UUID

import httpx2

from gateway_rest_client import (
    AudioEncoding,
    AudioFormat,
    CreateSessionRequest,
    GatewayRestClient,
    OpenSessionRequest,
    OpenVoiceSessionRequest,
    SessionChannel,
    VoiceSessionSnapshotResponse,
    VoiceSessionStatus,
    VoiceTurnResponse,
)
from gateway_rpc_client import GatewayRpcClient, connect_gateway
from gateway_rpc_client.models import (
    Activation,
    SessionEvent,
    VoiceEventMessage,
    VoiceTranscriptPartial,
    VoiceTurnCommandResult,
)
from voice.gateway.framing import MediaFrame
from voice.gateway.media import MediaTransport

logger = logging.getLogger(__name__)


class GatewayVoiceSession:
    def __init__(
        self,
        rest: GatewayRestClient,
        rpc: GatewayRpcClient,
        media: MediaTransport,
        snapshot: VoiceSessionSnapshotResponse,
        http: httpx2.AsyncClient,
    ) -> None:
        self._rest = rest
        self._rpc = rpc
        self._media = media
        self._snapshot = snapshot
        self._last_sequence = snapshot.last_sequence
        self._http = http
        self._closed = False

    @classmethod
    async def connect(
        cls,
        url: str,
        *,
        token: str,
        device_id: str,
        channel: str = "voice",
        new_session: bool = False,
        inactivity_timeout_seconds: float = 1800,
        input_sample_rate: int = 16_000,
        output_sample_rate: int = 24_000,
    ) -> Self:
        http = httpx2.AsyncClient()
        rest = GatewayRestClient(http, url, credentials={"GatewayToken": token})
        rpc: GatewayRpcClient | None = None
        media: MediaTransport | None = None
        try:
            existing = await rest.list_voice_sessions(
                device_id=device_id,
                status=VoiceSessionStatus.OPEN,
            )
            if new_session:
                for open_voice_session in existing.voice_sessions:
                    await rest.close_voice_session(open_voice_session.id)
            if existing.voice_sessions and not new_session:
                voice_session = existing.voice_sessions[0]
            else:
                session_id = await _resolve_conversation_session(
                    rest,
                    channel,
                    new_session=new_session,
                    inactivity_timeout_seconds=inactivity_timeout_seconds,
                )
                audio_input = AudioFormat(
                    encoding=AudioEncoding.PCM_S16LE,
                    sample_rate=input_sample_rate,
                    channels=1,
                )
                audio_output = AudioFormat(
                    encoding=AudioEncoding.PCM_S16LE,
                    sample_rate=output_sample_rate,
                    channels=1,
                )
                request = OpenVoiceSessionRequest(
                    session_id=session_id,
                    device_id=device_id,
                    input_formats=[audio_input],
                    output_formats=[audio_output],
                )
                voice_session = await rest.open_voice_session(request)
            rpc = await connect_gateway(url, token=token)
            await rpc.subscription.subscribe(session_id=voice_session.session_id)
            snapshot = await rest.get_voice_session(voice_session.id)
            logger.info(
                "Voice session %s is open with %d turn(s) at sequence %d",
                voice_session.id,
                len(snapshot.turns),
                snapshot.last_sequence,
            )
            media = await MediaTransport.connect(url, voice_session.media_path, token)
            return cls(rest, rpc, media, snapshot, http)
        except BaseException:
            if media is not None:
                await media.close()
            if rpc is not None:
                await rpc.close()
            await http.aclose()
            raise

    @property
    def id(self) -> UUID:
        return self._snapshot.voice_session.id

    @property
    def session_id(self) -> UUID:
        return self._snapshot.voice_session.session_id

    @property
    def input_sample_rate(self) -> int:
        return self._snapshot.voice_session.input_format.sample_rate

    @property
    def output_sample_rate(self) -> int:
        return self._snapshot.voice_session.output_format.sample_rate

    @property
    def output_channels(self) -> int:
        return self._snapshot.voice_session.output_format.channels

    @property
    def active_turn(self) -> VoiceTurnResponse | None:
        active_turn_id = self._snapshot.active_turn_id
        return next(
            (turn for turn in self._snapshot.turns if turn.id == active_turn_id),
            None,
        )

    async def voice_events(self) -> AsyncIterator[VoiceEventMessage]:
        async for event in self._rpc.voice.event():
            if event.voice_session_id != self.id:
                logger.debug(
                    "Dropping %s: it belongs to voice session %s",
                    event.type,
                    event.voice_session_id,
                )
                continue
            match event:
                case VoiceTranscriptPartial():
                    logger.debug("Received %s revision %d", event.type, event.revision)
                case _ if event.sequence > self._last_sequence:
                    self._last_sequence = event.sequence
                    logger.info("Received %s sequence %d", event.type, event.sequence)
                case _:
                    logger.info(
                        "Dropping %s: sequence %d was already seen (watermark %d)",
                        event.type,
                        event.sequence,
                        self._last_sequence,
                    )
                    continue
            yield event

    def conversation_events(self) -> AsyncIterator[SessionEvent]:
        return self._rpc.session.event()

    def media_frames(self) -> AsyncIterator[MediaFrame]:
        return self._media.frames()

    async def start_turn(
        self,
        activation: Activation,
        pre_roll_sequence: int | None,
    ) -> VoiceTurnCommandResult:
        return await self._rpc.voice.turn.start(
            voice_session_id=self.id,
            activation=activation,
            pre_roll_sequence=pre_roll_sequence,
        )

    async def turn_index(self, voice_turn_id: UUID) -> int:
        for turn in self._snapshot.turns:
            if turn.id == voice_turn_id:
                return turn.index
        # Only consumed events advance the watermark: a snapshot taken while
        # later events are already on their way to the subscriber would
        # otherwise make them look like history and drop them.
        snapshot = await self._rest.get_voice_session(self.id)
        self._snapshot = snapshot
        for turn in snapshot.turns:
            if turn.id == voice_turn_id:
                return turn.index
        raise RuntimeError(f"Voice turn {voice_turn_id} is missing from the snapshot")

    async def interrupt(self, voice_turn_id: UUID, input_sequence: int | None) -> None:
        await self._rpc.voice.turn.interrupt(
            voice_turn_id=voice_turn_id,
            input_sequence=input_sequence,
        )

    async def playback_completed(self, voice_turn_id: UUID) -> None:
        await self._rpc.voice.turn.playback_completed(voice_turn_id=voice_turn_id)

    async def send_input(
        self,
        turn_index: int,
        sequence: int,
        payload: bytes,
    ) -> None:
        await self._media.send_input(turn_index, sequence, payload)

    async def end_input(self, turn_index: int, sequence: int) -> None:
        await self._media.end_input(turn_index, sequence)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._rest.close_voice_session(self.id)
        finally:
            try:
                await self._media.close()
            finally:
                try:
                    await self._rpc.subscription.unsubscribe(session_id=self.session_id)
                finally:
                    try:
                        await self._rpc.close()
                    finally:
                        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


async def _resolve_conversation_session(
    rest: GatewayRestClient,
    channel: str,
    *,
    new_session: bool,
    inactivity_timeout_seconds: float,
) -> UUID:
    channel_ref = SessionChannel(name=channel)
    if new_session:
        request = CreateSessionRequest(
            channel=channel_ref,
            inactivity_timeout_seconds=inactivity_timeout_seconds,
        )
        session = await rest.create_session(request)
    else:
        request = OpenSessionRequest(
            channel=channel_ref,
            inactivity_timeout_seconds=inactivity_timeout_seconds,
        )
        session = await rest.open_session(request)
    return session.id
