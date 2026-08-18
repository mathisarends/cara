import asyncio
import logging
from collections.abc import AsyncIterator

from voice.audio.buffered_input import AudioReader, BufferedAudioInput
from voice.events import (
    UserSpeechEnded,
    UserSpeechStarted,
    UserTranscriptionCompleted,
    UserTranscriptionRequested,
    UserTranscriptionUpdated,
    VoiceTurnFailed,
    VoiceTurnTimedOut,
)
from voice.events.bus import EventBus
from voice.stt.port import SpeechToText
from voice.transcription import Transcription

logger = logging.getLogger(__name__)


class SpeechToTextBridge:
    """Consumes turn-scoped audio readers and publishes transcription events."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        buffered_audio_input: BufferedAudioInput,
        speech_to_text: SpeechToText,
    ) -> None:
        self._event_bus = event_bus
        self._buffered_audio_input = buffered_audio_input
        self._speech_to_text = speech_to_text

        event_bus.on(UserTranscriptionRequested, self._on_transcription_requested)

    async def _on_transcription_requested(
        self, event: UserTranscriptionRequested
    ) -> None:
        reader = await self._buffered_audio_input.open_reader(
            from_sequence=event.sequence,
            pre_roll_seconds=event.pre_roll_seconds,
        )
        transcriptions = self._speech_to_text.transcribe(_audio_chunks(reader))
        try:
            try:
                first = await asyncio.wait_for(
                    anext(transcriptions),
                    timeout=event.speech_start_timeout,
                )
            except TimeoutError:
                logger.debug(
                    "Turn %d: no speech within %.1fs, timing out",
                    event.turn_id,
                    event.speech_start_timeout,
                )
                await self._event_bus.dispatch(VoiceTurnTimedOut(turn_id=event.turn_id))
                return
            except StopAsyncIteration:
                return

            await self._publish_transcription(event.turn_id, first)
            await self._event_bus.dispatch(UserSpeechStarted())
            final_text = first.text if first.is_final else None
            while final_text is None:
                update = await anext(transcriptions)
                await self._publish_transcription(event.turn_id, update)
                if update.is_final:
                    final_text = update.text

            await self._event_bus.dispatch(UserSpeechEnded())
            await self._event_bus.dispatch(
                UserTranscriptionCompleted(
                    turn_id=event.turn_id,
                    text=final_text,
                )
            )
        except asyncio.CancelledError:
            raise
        except StopAsyncIteration:
            return
        except Exception as error:
            logger.exception("Transcription failed for voice turn %d", event.turn_id)
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=event.turn_id, message=str(error))
            )
        finally:
            await transcriptions.aclose()
            await reader.aclose()

    async def _publish_transcription(self, turn_id: int, update: Transcription) -> None:
        await self._event_bus.dispatch(
            UserTranscriptionUpdated(
                turn_id=turn_id,
                text=update.text,
                is_final=update.is_final,
                kind=update.kind,
            )
        )


async def _audio_chunks(reader: AudioReader) -> AsyncIterator[bytes]:
    async for frame in reader:
        yield frame.pcm
