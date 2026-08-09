import argparse
import asyncio
import logging
from uuid import UUID

from dotenv import load_dotenv
from transitbus import EventBus

from gateway_client import (
    ChatCompletedEvent,
    ChatDeltaEvent,
    ChatRequest,
    GatewayClient,
    GatewayError,
    GatewayEventStream,
    SessionCreateRequest,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
    TurnFailedEvent,
)
from voice import VoiceSession
from voice.audio import (
    AudioOutput,
    AudioPlayer,
    EarconPlayer,
    MicrophoneRecorder,
    MicrophoneStream,
)
from voice.audio.device import PortAudioDevice
from voice.audio.sonos import SonosAudioSink
from voice.speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechInput,
    SpeechOutput,
    SpeechSettings,
)
from voice.wakeword import WakeWord, WakeWordListener

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class _GatewayResponder:
    """Adapts one persistent gateway session to VoiceSession's text interface."""

    def __init__(self, client: GatewayClient, session_id: UUID) -> None:
        self._client = client
        self._session_id = session_id

    async def respond(self, text: str) -> str:
        async with self._client.event_stream(self._session_id) as events:
            await self._client.sessions.start_chat(
                self._session_id,
                ChatRequest(text=text, metadata={"channel": "voice"}),
            )
            try:
                return await self._receive_response(events)
            except asyncio.CancelledError:
                # The gateway currently has no per-turn cancellation endpoint. Keep
                # consuming until it releases the session, otherwise a barge-in
                # would immediately collide with the still-running gateway turn.
                logger.info("Voice turn interrupted; waiting for gateway cleanup.")
                await self._receive_response(events)
                raise

    async def _receive_response(self, events: GatewayEventStream) -> str:
        async for event in events:
            match event:
                case ChatDeltaEvent(data=data):
                    logger.debug("Gateway response delta: %s", data.text)
                case ChatCompletedEvent(data=data):
                    if data.finish_reason != "tool_calls":
                        return data.text
                case ToolCallStartedEvent(data=data):
                    logger.info("[tool] %s %s", data.name, data.arguments)
                case ToolCallCompletedEvent(data=data):
                    status = "error" if data.is_error else "ok"
                    logger.info("[tool] %s -> %s", data.name, status)
                case TurnFailedEvent(data=data):
                    raise GatewayError(f"{data.code}: {data.message}")

        raise GatewayError("Gateway event stream ended before the turn completed.")


async def main(base_url: str = DEFAULT_GATEWAY_URL) -> None:
    load_dotenv(override=True)
    event_bus = EventBus()
    audio_device = PortAudioDevice()
    microphone = MicrophoneStream(device=audio_device)
    sonos_sink = SonosAudioSink()
    audio_player = AudioPlayer(
        sonos_sink,
        active_output=AudioOutput.SONOS,
    )
    speech_settings = SpeechSettings(language="de")

    try:
        async with GatewayClient(base_url) as client:
            session = await client.sessions.create_session(
                SessionCreateRequest(metadata={"channel": "voice"})
            )
            logger.info("Connected to %s (voice session %s)", base_url, session.id)
            logger.info(
                'Listening for the wake word "Hey Mycroft". Press Ctrl+C to quit.'
            )

            voice_session = VoiceSession(
                agent=_GatewayResponder(client, session.id),
                speech_input=SpeechInput(
                    MicrophoneRecorder(microphone),
                    OpenAISpeechToText(),
                    speech_settings,
                    event_bus,
                ),
                speech_output=SpeechOutput(
                    OpenAITextToSpeech(),
                    audio_player,
                    speech_settings,
                    event_bus,
                ),
                wake_word_listener=WakeWordListener(
                    microphone,
                    wake_word=WakeWord.HEY_MYCROFT,
                    sensitivity=0.5,
                ),
                event_bus=event_bus,
                earcons=EarconPlayer(audio_player),
            )
            await voice_session.run()
    finally:
        await sonos_sink.close()
        microphone.close()
        audio_device.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Talk to Cara through the gateway using microphone and speakers."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_GATEWAY_URL,
        help=f"Gateway base URL (default: {DEFAULT_GATEWAY_URL}).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse_args().url))
    except (KeyboardInterrupt, EOFError):
        print()
    except GatewayError as exc:
        raise SystemExit(f"Gateway error: {exc}") from exc
