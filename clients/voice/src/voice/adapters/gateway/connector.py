import logging
from contextlib import AsyncExitStack

import httpx2

from gateway_rest_client import (
    CreateSessionRequest,
    GatewayRestClient,
    OpenVoiceSessionRequest,
    SessionChannel,
    VoiceSessionStatus,
)
from gateway_rpc_client import connect_gateway
from voice.adapters.gateway.backend import GatewayVoiceBackend
from voice.adapters.gateway.mapper import gateway_audio_format
from voice.adapters.gateway.media import MediaTransport
from voice.backend import BackendConnectionOptions, VoiceBackendConnector

logger = logging.getLogger(__name__)


class GatewayVoiceBackendConnector(VoiceBackendConnector):
    """Opens a fresh Gateway voice session for the configured room."""

    def __init__(self, url: str, *, token: str) -> None:
        self._url = url
        self._token = token

    async def connect(self, options: BackendConnectionOptions) -> GatewayVoiceBackend:
        http = httpx2.AsyncClient()
        rest = GatewayRestClient(
            http, self._url, credentials={"GatewayToken": self._token}
        )
        resources = AsyncExitStack()
        try:
            # Every conversation starts from a clean context, so a leftover
            # voice session never carries an earlier one into this run.
            existing = await rest.list_voice_sessions(
                room=options.room,
                status=VoiceSessionStatus.OPEN,
            )
            for open_voice_session in existing.voice_sessions:
                await rest.close_voice_session(open_voice_session.id)
            session = await rest.create_session(
                CreateSessionRequest(
                    channel=SessionChannel(name=options.channel),
                    inactivity_timeout_seconds=options.inactivity_timeout_seconds,
                )
            )
            voice_session = await rest.open_voice_session(
                OpenVoiceSessionRequest(
                    session_id=session.id,
                    room=options.room,
                    input_formats=[gateway_audio_format(options.input_format)],
                    output_formats=[gateway_audio_format(options.output_format)],
                )
            )
            rpc = await connect_gateway(self._url, token=self._token)
            await resources.enter_async_context(rpc)
            # Subscribing before loading the snapshot means no event can fall
            # between the two; the watermark drops the ones seen twice.
            await rpc.subscription.subscribe(session_id=voice_session.session_id)
            snapshot = await rest.get_voice_session(voice_session.id)
            logger.info(
                "Voice session %s is open with %d turn(s) at sequence %d",
                voice_session.id,
                len(snapshot.turns),
                snapshot.last_sequence,
            )
            media_channel = await resources.enter_async_context(
                rpc.voice.media(voice_session_id=str(voice_session.id))
            )
            return GatewayVoiceBackend(
                rest=rest,
                rpc=rpc,
                media=MediaTransport(media_channel),
                snapshot=snapshot,
                http=http,
                resources=resources,
            )
        except BaseException:
            await resources.aclose()
            await http.aclose()
            raise
