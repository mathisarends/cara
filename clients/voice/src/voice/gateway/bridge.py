import asyncio
import logging
from collections.abc import Coroutine
from contextlib import suppress
from uuid import UUID

from gateway_rest_client import VoiceTurnStatus
from gateway_rpc_client.models import (
    Activation,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
    VoiceAssistantAudioCompleted,
    VoiceAssistantAudioStarted,
    VoiceSessionClosed,
    VoiceTranscriptFinal,
    VoiceTranscriptPartial,
    VoiceTurnCancelled,
    VoiceTurnCompleted,
    VoiceTurnDiscarded,
    VoiceTurnFailed,
    VoiceTurnStarted,
)
from voice.activation import ActivationKind
from voice.audio import BufferedAudioInput
from voice.audio.buffered_input import AudioReader
from voice.events import (
    AssistantAudioChunk,
    AssistantAudioCompleted,
    AssistantAudioStarted,
    AssistantPlaybackCompleted,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    SessionEnded,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTranscriptionCompleted,
    UserTranscriptionUpdated,
    UserTurnStarted,
    VoiceTurnInterrupted,
    VoiceTurnTimedOut,
)
from voice.events import (
    VoiceTurnFailed as LocalVoiceTurnFailed,
)
from voice.events.bus import EventBus
from voice.events.models import (
    VoiceResourcesClosing,
    VoiceTurnEnded,
    VoiceTurnRequested,
)
from voice.events.models import (
    VoiceTurnStarted as LocalVoiceTurnStarted,
)
from voice.gateway.framing import MediaFrameKind
from voice.gateway.session import GatewayVoiceSession
from voice.transcription import TranscriptionKind

logger = logging.getLogger(__name__)


class GatewayVoiceBridge:
    def __init__(
        self,
        event_bus: EventBus,
        session: GatewayVoiceSession,
        audio_input: BufferedAudioInput,
        *,
        pre_roll_seconds: float = 0.16,
    ) -> None:
        self._event_bus = event_bus
        self._session = session
        self._audio_input = audio_input
        self._pre_roll_seconds = pre_roll_seconds
        self._active_turn_id: UUID | None = None
        self._active_turn_index: int | None = None
        self._speech_started_turn_id: UUID | None = None
        self._audio_started_turn_id: UUID | None = None
        self._input_reader: AudioReader | None = None
        self._input_task: asyncio.Task[None] | None = None
        self._input_timeout_task: asyncio.Task[None] | None = None
        self._last_input_sequence = -1
        self._tasks: list[asyncio.Task[None]] = []
        self._turn_lock = asyncio.Lock()
        self._closed = False

        event_bus.on_request(VoiceTurnRequested, self._on_turn_requested)
        event_bus.on(AssistantPlaybackCompleted, self._on_playback_completed)
        event_bus.on(SessionEnded, self._on_session_ended)
        event_bus.on(VoiceResourcesClosing, self._on_resources_closing)

    @property
    def active_turn_id(self) -> UUID | None:
        return self._active_turn_id

    async def start(self) -> None:
        if self._tasks:
            return
        await self._restore_active_turn()
        self._tasks = [
            asyncio.create_task(
                self._pump(self._pump_voice_events(), "voice event"),
                name="voice-events",
            ),
            asyncio.create_task(
                self._pump(self._pump_conversation_events(), "conversation event"),
                name="voice-conversation-events",
            ),
            asyncio.create_task(
                self._pump(self._pump_media(), "media"),
                name="voice-media",
            ),
        ]

    async def _restore_active_turn(self) -> None:
        turn = self._session.active_turn
        if turn is None:
            return
        self._active_turn_id = turn.id
        self._active_turn_index = turn.index
        await self._event_bus.dispatch(LocalVoiceTurnStarted(turn_id=turn.id))
        match turn.status:
            case VoiceTurnStatus.LISTENING:
                await self._event_bus.dispatch(UserTurnStarted())
                await self._start_input(None)
            case VoiceTurnStatus.TRANSCRIBING:
                await self._event_bus.dispatch(UserSpeechEnded())
            case VoiceTurnStatus.WAITING_FOR_ASSISTANT | VoiceTurnStatus.SPEAKING:
                if turn.transcript is not None:
                    await self._event_bus.dispatch(
                        UserTranscriptionCompleted(
                            turn_id=turn.id,
                            text=turn.transcript,
                        )
                    )
                await self._event_bus.dispatch(AssistantTurnStarted())
                await self._event_bus.dispatch(
                    AssistantResponseStarted(turn_id=turn.id)
                )
                if turn.status is VoiceTurnStatus.SPEAKING:
                    await self._start_assistant_audio(turn.id)

    async def _pump(self, stream: Coroutine[None, None, None], kind: str) -> None:
        """Run one gateway stream, releasing the active turn if it fails.

        A stream that dies leaves the channel unable to hear the rest of the
        turn, so the turn is failed rather than left open forever, which would
        make the channel ignore every later activation.
        """
        try:
            await stream
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("The %s stream failed", kind)
            await self._abandon_active_turn(str(error))

    async def _abandon_active_turn(self, message: str) -> None:
        turn_id = self._active_turn_id
        if turn_id is None:
            return
        await self._event_bus.dispatch(
            LocalVoiceTurnFailed(turn_id=turn_id, message=message)
        )
        await self._finish_turn(turn_id)

    async def interrupt(self, sequence: int) -> None:
        turn_id = self._active_turn_id
        if turn_id is None:
            return
        await self._stop_input()
        await self._event_bus.dispatch(VoiceTurnInterrupted(turn_id=turn_id))
        await self._session.interrupt(turn_id, sequence)
        await self._finish_turn(turn_id)
        await self._event_bus.request(
            VoiceTurnRequested(
                sequence=sequence,
                activation=ActivationKind.BARGE_IN,
            )
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._stop_input()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _on_turn_requested(self, event: VoiceTurnRequested) -> None:
        async with self._turn_lock:
            if self._closed or self._active_turn_id is not None:
                return
            activation = Activation(event.activation.value)
            result = await self._session.start_turn(activation, event.sequence)
            turn_index = await self._session.turn_index(result.voice_turn_id)
            self._active_turn_id = result.voice_turn_id
            self._active_turn_index = turn_index
            await self._event_bus.dispatch(
                LocalVoiceTurnStarted(turn_id=result.voice_turn_id)
            )
            await self._event_bus.dispatch(UserTurnStarted())
            await self._start_input(event.sequence, event.speech_start_timeout)

    async def _start_input(
        self,
        sequence: int | None,
        speech_start_timeout: float | None = None,
    ) -> None:
        reader = await self._audio_input.open_reader(
            from_sequence=sequence,
            pre_roll_seconds=self._pre_roll_seconds,
        )
        self._input_reader = reader
        self._last_input_sequence = -1
        self._input_task = asyncio.create_task(
            self._upload_input(reader),
            name=f"voice-input-{self._active_turn_id}",
        )
        if speech_start_timeout is not None:
            self._input_timeout_task = asyncio.create_task(
                self._end_input_after(speech_start_timeout),
                name=f"voice-input-timeout-{self._active_turn_id}",
            )

    async def _upload_input(self, reader: AudioReader) -> None:
        turn_index = self._active_turn_index
        if turn_index is None:
            return
        try:
            async for frame in reader:
                self._last_input_sequence = frame.sequence
                await self._session.send_input(
                    turn_index,
                    frame.sequence,
                    frame.pcm,
                )
            await self._session.end_input(turn_index, self._last_input_sequence + 1)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            turn_id = self._active_turn_id
            if turn_id is not None:
                await self._event_bus.dispatch(
                    LocalVoiceTurnFailed(turn_id=turn_id, message=str(error))
                )

    async def _stop_input(self) -> None:
        timeout_task, self._input_timeout_task = self._input_timeout_task, None
        task, self._input_task = self._input_task, None
        reader, self._input_reader = self._input_reader, None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if reader is not None:
            await reader.aclose()
        if timeout_task is not None and timeout_task is not asyncio.current_task():
            timeout_task.cancel()
            await asyncio.gather(timeout_task, return_exceptions=True)

    async def _end_input_after(self, timeout_seconds: float) -> None:
        await asyncio.sleep(timeout_seconds)
        turn_index = self._active_turn_index
        if turn_index is None:
            return
        await self._stop_input()
        await self._session.end_input(turn_index, self._last_input_sequence + 1)

    async def _pump_voice_events(self) -> None:
        async for event in self._session.voice_events():
            match event:
                case VoiceTurnStarted():
                    await self._voice_turn_started(event)
                case VoiceTranscriptPartial():
                    await self._start_user_speech(event.voice_turn_id)
                    await self._event_bus.dispatch(
                        UserTranscriptionUpdated(
                            turn_id=event.voice_turn_id,
                            text=event.text,
                            is_final=False,
                            kind=TranscriptionKind.UPDATE,
                        )
                    )
                case VoiceTranscriptFinal():
                    await self._stop_input()
                    await self._start_user_speech(event.voice_turn_id)
                    await self._event_bus.dispatch(UserSpeechEnded())
                    await self._event_bus.dispatch(
                        UserTranscriptionCompleted(
                            turn_id=event.voice_turn_id,
                            text=event.text,
                        )
                    )
                    await self._event_bus.dispatch(AssistantTurnStarted())
                    await self._event_bus.dispatch(
                        AssistantResponseStarted(turn_id=event.voice_turn_id)
                    )
                case VoiceAssistantAudioStarted():
                    await self._start_assistant_audio(event.voice_turn_id)
                case VoiceAssistantAudioCompleted():
                    pass
                case VoiceTurnDiscarded():
                    await self._stop_input()
                    await self._event_bus.dispatch(
                        VoiceTurnTimedOut(turn_id=event.voice_turn_id)
                    )
                    await self._finish_turn(event.voice_turn_id)
                case VoiceTurnCancelled() | VoiceTurnCompleted():
                    await self._finish_turn(event.voice_turn_id)
                case VoiceTurnFailed():
                    await self._event_bus.dispatch(
                        LocalVoiceTurnFailed(
                            turn_id=event.voice_turn_id,
                            message=event.message,
                        )
                    )
                    await self._finish_turn(event.voice_turn_id)
                case VoiceSessionClosed():
                    return

    async def _voice_turn_started(self, event: VoiceTurnStarted) -> None:
        async with self._turn_lock:
            if self._active_turn_id == event.voice_turn_id:
                return
            if self._active_turn_id is not None:
                return
            self._active_turn_id = event.voice_turn_id
            self._active_turn_index = await self._session.turn_index(
                event.voice_turn_id
            )
            await self._event_bus.dispatch(
                LocalVoiceTurnStarted(turn_id=event.voice_turn_id)
            )
            if event.activation is Activation.PROACTIVE:
                await self._event_bus.dispatch(AssistantTurnStarted())
                await self._event_bus.dispatch(
                    AssistantResponseStarted(turn_id=event.voice_turn_id)
                )
            else:
                await self._event_bus.dispatch(UserTurnStarted())
                await self._start_input(None)

    async def _pump_conversation_events(self) -> None:
        async for event in self._session.conversation_events():
            turn_id = self._active_turn_id
            if turn_id is None:
                continue
            metadata = event.metadata or {}
            if metadata.get("voice_turn_id") != str(turn_id):
                continue
            match event:
                case ChatDelta():
                    await self._event_bus.dispatch(
                        AssistantTextChunk(turn_id=turn_id, chunk=event.text)
                    )
                case ChatCompleted():
                    await self._event_bus.dispatch(
                        AssistantTextCompleted(turn_id=turn_id, text=event.text)
                    )
                case ToolCallStarted():
                    await self._event_bus.dispatch(
                        AssistantToolStarted(turn_id=turn_id, name=event.name)
                    )
                case ToolCallCompleted():
                    await self._event_bus.dispatch(
                        AssistantToolCompleted(turn_id=turn_id, name=event.name)
                    )

    async def _pump_media(self) -> None:
        async for frame in self._session.media_frames():
            turn_id = self._active_turn_id
            if turn_id is None or frame.voice_turn_index != self._active_turn_index:
                continue
            # Media and lifecycle events travel on separate sockets, so audio
            # can arrive before voice.assistant_audio.started does.
            await self._start_assistant_audio(turn_id)
            if frame.kind is MediaFrameKind.OUTPUT_PCM:
                await self._event_bus.dispatch(
                    AssistantAudioChunk(turn_id=turn_id, chunk=frame.payload)
                )
            elif frame.kind is MediaFrameKind.OUTPUT_END:
                await self._event_bus.dispatch(AssistantAudioCompleted(turn_id=turn_id))

    async def _start_user_speech(self, turn_id: UUID) -> None:
        """Announce the first evidence that the user is actually speaking.

        Transcription is what distinguishes speech from an open microphone, so
        a follow-up window stays open until the gateway hears something.
        """
        if self._speech_started_turn_id == turn_id:
            return
        self._speech_started_turn_id = turn_id
        await self._event_bus.dispatch(UserSpeechStarted())

    async def _start_assistant_audio(self, turn_id: UUID) -> None:
        if self._audio_started_turn_id == turn_id:
            return
        self._audio_started_turn_id = turn_id
        await self._event_bus.dispatch(
            AssistantAudioStarted(
                turn_id=turn_id,
                sample_rate=self._session.output_sample_rate,
                channels=self._session.output_channels,
            )
        )

    async def _on_playback_completed(
        self,
        event: AssistantPlaybackCompleted,
    ) -> None:
        if event.turn_id == self._active_turn_id:
            await self._session.playback_completed(event.turn_id)

    async def _finish_turn(self, turn_id: UUID) -> None:
        if turn_id != self._active_turn_id:
            return
        await self._stop_input()
        self._active_turn_id = None
        self._active_turn_index = None
        await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))

    async def _on_session_ended(self, _: SessionEnded) -> None:
        turn_id = self._active_turn_id
        if turn_id is not None:
            with suppress(Exception):
                await self._session.interrupt(turn_id, None)

    async def _on_resources_closing(self, _: VoiceResourcesClosing) -> None:
        await self.close()
