import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from enum import Enum, auto
from uuid import UUID

from gateway.features.conversation.application import (
    ConversationEventType,
    EventSource,
    TurnService,
)
from gateway.features.conversation.domain import NoActiveTurnError
from gateway.features.voice.application.events import VoiceEvent, VoiceEventType
from gateway.features.voice.application.ports import (
    MediaSessions,
    SpeechToText,
    TextToSpeech,
    VoiceEventPublisher,
)
from gateway.features.voice.application.voice_session_service import VoiceSessionService
from gateway.features.voice.domain import (
    Activation,
    MediaNotConnectedError,
    VoiceSessionRepository,
    VoiceSessionStatus,
    VoiceTurn,
    VoiceTurnNotFoundError,
)
from gateway.shared import UnitOfWork

type _SpeechQueue = asyncio.Queue[str | _Flush | None]


class VoiceTurnService:
    def __init__(
        self,
        repositories: UnitOfWork[VoiceSessionRepository],
        sessions: VoiceSessionService,
        turns: TurnService,
        events: VoiceEventPublisher,
        media: MediaSessions,
        conversation_events: EventSource,
        speech_to_text: SpeechToText,
        text_to_speech: TextToSpeech,
        input_queue_size: int,
        conversation_follow_up_delay_seconds: float,
        conversation_inactivity_timeout_seconds: float,
        conversation_inactivity_countdown_seconds: int,
    ) -> None:
        self._repositories = repositories
        self._sessions = sessions
        self._turns = turns
        self._events = events
        self._media = media
        self._conversation_events = conversation_events
        self._speech_to_text = speech_to_text
        self._text_to_speech = text_to_speech
        self._input_queue_size = input_queue_size
        self._conversation_follow_up_delay_seconds = (
            conversation_follow_up_delay_seconds
        )
        self._conversation_inactivity_timeout_seconds = (
            conversation_inactivity_timeout_seconds
        )
        self._conversation_inactivity_countdown_seconds = (
            conversation_inactivity_countdown_seconds
        )
        self._partial_revisions: dict[UUID, int] = {}
        self._input_sequences: dict[UUID, int] = {}
        self._input_queues: dict[UUID, asyncio.Queue[bytes | None]] = {}
        self._tasks: dict[UUID, set[asyncio.Task[None]]] = {}
        self._active_conversations: set[UUID] = set()
        self._conversation_timeout_tasks: dict[UUID, asyncio.Task[None]] = {}
        self._timed_out_turns: set[UUID] = set()

    async def start(
        self,
        voice_session_id: UUID,
        activation: Activation,
    ) -> VoiceTurn:
        if not self._media.connected(voice_session_id):
            raise MediaNotConnectedError(
                f"Voice session {voice_session_id} has no media connection"
            )
        voice_session = await self._sessions.get(voice_session_id)
        turn = voice_session.start_turn(activation)
        conversation_started = voice_session_id not in self._active_conversations
        if conversation_started:
            self._active_conversations.add(voice_session_id)
            conversation_sequence = voice_session.next_sequence()
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        if conversation_started:
            await self._events.publish_voice(
                VoiceEvent(
                    VoiceEventType.CONVERSATION_STARTED,
                    voice_session.id,
                    voice_session.session_id,
                    {},
                    sequence=conversation_sequence,
                )
            )
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TURN_STARTED,
                voice_session.id,
                voice_session.session_id,
                {"activation": activation},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(self._input_queue_size)
        self._input_queues[turn.id] = queue
        self._start_task(turn.id, self._transcribe(turn.id, queue))
        if activation is not Activation.PROACTIVE:
            self._start_conversation_timeout(voice_session.id, turn.id)
        return turn

    async def start_proactive_in_room(
        self,
        room: str,
        *,
        text: str,
    ) -> VoiceTurn | None:
        sessions = await self._sessions.list(
            room=room,
            status=VoiceSessionStatus.OPEN,
        )
        connected = tuple(
            session for session in sessions if self._media.connected(session.id)
        )
        if not connected:
            return None
        return await self.start_proactive(connected[0].id, text=text)

    async def start_proactive(
        self,
        voice_session_id: UUID,
        *,
        text: str,
    ) -> VoiceTurn:
        if not self._media.connected(voice_session_id):
            raise MediaNotConnectedError(
                f"Voice session {voice_session_id} has no media connection"
            )
        voice_session = await self._sessions.get(voice_session_id)
        turn = voice_session.start_proactive_turn()
        conversation_started = voice_session_id not in self._active_conversations
        if conversation_started:
            self._active_conversations.add(voice_session_id)
            conversation_sequence = voice_session.next_sequence()
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        if conversation_started:
            await self._events.publish_voice(
                VoiceEvent(
                    VoiceEventType.CONVERSATION_STARTED,
                    voice_session.id,
                    voice_session.session_id,
                    {},
                    sequence=conversation_sequence,
                )
            )
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TURN_STARTED,
                voice_session.id,
                voice_session.session_id,
                {"activation": Activation.PROACTIVE},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )

        ready = asyncio.Event()
        speech_task = self._start_task(
            turn.id,
            self._conversation_to_speech(voice_session.id, turn.id, ready),
        )
        await ready.wait()
        await self._turns.start_scheduled(
            session_id=voice_session.session_id,
            text=text,
        )
        await speech_task
        return turn

    async def partial_transcript(self, voice_turn_id: UUID, text: str) -> None:
        voice_session, turn = await self._find_turn(voice_turn_id)
        if text.strip():
            self._cancel_conversation_timeout(voice_session.id)
        revision = self._partial_revisions.get(turn.id, 0) + 1
        self._partial_revisions[turn.id] = revision
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TRANSCRIPT_PARTIAL,
                voice_session.id,
                voice_session.session_id,
                {"text": text},
                voice_turn_id=turn.id,
                revision=revision,
            )
        )

    async def final_transcript(self, voice_turn_id: UUID, text: str) -> VoiceTurn:
        voice_session, turn = await self._find_turn(voice_turn_id)
        normalized = " ".join(text.split())
        if normalized:
            self._cancel_conversation_timeout(voice_session.id)
        if not normalized:
            turn.discard()
            event_type = VoiceEventType.TURN_DISCARDED
            data: dict[str, object] = {}
        else:
            ready = asyncio.Event()
            speech_task = self._start_task(
                turn.id,
                self._conversation_to_speech(
                    voice_session.id,
                    turn.id,
                    ready,
                ),
            )
            await ready.wait()
            user_message_id = await self._turns.start(
                session_id=voice_session.session_id,
                text=normalized,
            )
            turn.transcribe(normalized, user_message_id)
            event_type = VoiceEventType.TRANSCRIPT_FINAL
            data = {"text": normalized, "user_message_id": user_message_id}
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                event_type,
                voice_session.id,
                voice_session.session_id,
                data,
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )
        self._partial_revisions.pop(turn.id, None)
        if not normalized:
            self._cancel_tasks(turn.id)
            if turn.id in self._timed_out_turns:
                self._timed_out_turns.discard(turn.id)
                await self._end_conversation(voice_session.id, "inactivity_timeout")
        elif speech_task.done() and (error := speech_task.exception()) is not None:
            await self._fail(turn.id, type(error).__name__, str(error))
        return turn

    async def interrupt(self, voice_turn_id: UUID) -> VoiceTurn:
        voice_session, turn = await self._find_turn(voice_turn_id)
        if turn.user_message_id is not None:
            # The conversation turn may already be done while its answer is
            # still being spoken.
            with suppress(NoActiveTurnError):
                await self._turns.cancel(voice_session.session_id)
        turn.cancel()
        sequence = voice_session.next_sequence()
        self._input_sequences.pop(turn.id, None)
        self._partial_revisions.pop(turn.id, None)
        self._input_queues.pop(turn.id, None)
        self._cancel_tasks(turn.id)
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TURN_CANCELLED,
                voice_session.id,
                voice_session.session_id,
                {"reason": "client"},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )
        return turn

    async def playback_completed(self, voice_turn_id: UUID) -> VoiceTurn:
        voice_session, turn = await self._find_turn(voice_turn_id)
        turn.complete()
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TURN_COMPLETED,
                voice_session.id,
                voice_session.session_id,
                {},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )
        await asyncio.sleep(self._conversation_follow_up_delay_seconds)
        current = await self._sessions.get(voice_session.id)
        if (
            self._media.connected(voice_session.id)
            and current.turns[-1].id == turn.id
            and current.active_turn is None
        ):
            await self.start(voice_session.id, Activation.FOLLOW_UP)
        return turn

    async def voice_session_id_for(self, voice_turn_id: UUID) -> UUID:
        voice_session, _ = await self._find_turn(voice_turn_id)
        return voice_session.id

    async def receive_media(
        self,
        voice_session_id: UUID,
        voice_turn_index: int,
        sequence: int,
        payload: bytes,
        *,
        end: bool,
    ) -> None:
        voice_session = await self._sessions.get(voice_session_id)
        turn = voice_session.active_turn
        # The client keeps streaming until it hears that input ended, so frames
        # for a finished turn or a closed input stream are still in flight.
        if turn is None or turn.index > voice_turn_index:
            return
        if turn.index != voice_turn_index:
            raise ValueError("Media frame does not belong to the active voice turn")
        queue = self._input_queues.get(turn.id)
        if queue is None:
            return
        previous = self._input_sequences.get(turn.id, -1)
        if sequence <= previous:
            raise ValueError("Media frame sequence must increase monotonically")
        self._input_sequences[turn.id] = sequence
        if end:
            turn.end_input()
            async with self._repositories() as repository:
                await repository.save(voice_session)
            await queue.put(None)
        else:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                await self._fail(
                    turn.id,
                    "input_overrun",
                    "The speech-to-text input queue is full",
                )

    async def media_disconnected(self, voice_session_id: UUID) -> None:
        voice_session = await self._sessions.get(voice_session_id)
        turn = voice_session.active_turn
        if turn is None:
            return
        if turn.user_message_id is not None:
            with suppress(NoActiveTurnError):
                await self._turns.cancel(voice_session.session_id)
        turn.cancel()
        sequence = voice_session.next_sequence()
        self._input_sequences.pop(turn.id, None)
        self._partial_revisions.pop(turn.id, None)
        self._input_queues.pop(turn.id, None)
        self._cancel_tasks(turn.id)
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TURN_CANCELLED,
                voice_session.id,
                voice_session.session_id,
                {"reason": "media_disconnected"},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )

    async def close(self) -> None:
        timeout_tasks = tuple(self._conversation_timeout_tasks.values())
        self._conversation_timeout_tasks.clear()
        for task in timeout_tasks:
            task.cancel()
        tasks = tuple(task for group in self._tasks.values() for task in group)
        for task in tasks:
            task.cancel()
        if timeout_tasks or tasks:
            await asyncio.gather(*timeout_tasks, *tasks, return_exceptions=True)

    def _start_conversation_timeout(
        self,
        voice_session_id: UUID,
        voice_turn_id: UUID,
    ) -> None:
        self._cancel_conversation_timeout(voice_session_id)
        task = asyncio.create_task(
            self._run_conversation_timeout(voice_session_id, voice_turn_id),
            name=f"voice-conversation-timeout-{voice_session_id}",
        )
        self._conversation_timeout_tasks[voice_session_id] = task

    def _cancel_conversation_timeout(self, voice_session_id: UUID) -> None:
        task = self._conversation_timeout_tasks.pop(voice_session_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _run_conversation_timeout(
        self,
        voice_session_id: UUID,
        voice_turn_id: UUID,
    ) -> None:
        timeout = self._conversation_inactivity_timeout_seconds
        deadline = asyncio.get_running_loop().time() + timeout
        first_tick = min(
            self._conversation_inactivity_countdown_seconds,
            int(timeout),
        )
        try:
            for remaining in range(first_tick, 0, -1):
                await asyncio.sleep(
                    max(deadline - remaining - asyncio.get_running_loop().time(), 0.0)
                )
                await self._publish_conversation_event(
                    voice_session_id,
                    VoiceEventType.CONVERSATION_INACTIVITY_COUNTDOWN,
                    {"remaining_seconds": remaining},
                )
            await asyncio.sleep(max(deadline - asyncio.get_running_loop().time(), 0.0))
            voice_session, turn = await self._find_turn(voice_turn_id)
            if voice_session.id != voice_session_id or turn.status.terminal:
                return
            queue = self._input_queues.get(voice_turn_id)
            if queue is None:
                return
            turn.end_input()
            async with self._repositories() as repository:
                await repository.save(voice_session)
            self._timed_out_turns.add(voice_turn_id)
            await queue.put(None)
        finally:
            current = asyncio.current_task()
            if self._conversation_timeout_tasks.get(voice_session_id) is current:
                self._conversation_timeout_tasks.pop(voice_session_id, None)

    async def _end_conversation(self, voice_session_id: UUID, reason: str) -> None:
        if voice_session_id not in self._active_conversations:
            return
        self._active_conversations.discard(voice_session_id)
        self._cancel_conversation_timeout(voice_session_id)
        await self._publish_conversation_event(
            voice_session_id,
            VoiceEventType.CONVERSATION_ENDED,
            {"reason": reason},
        )

    async def _publish_conversation_event(
        self,
        voice_session_id: UUID,
        event_type: VoiceEventType,
        data: dict[str, object],
    ) -> None:
        voice_session = await self._sessions.get(voice_session_id)
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                event_type,
                voice_session.id,
                voice_session.session_id,
                data,
                sequence=sequence,
            )
        )

    async def _transcribe(
        self,
        voice_turn_id: UUID,
        queue: asyncio.Queue[bytes | None],
    ) -> None:
        try:
            async for update in self._speech_to_text.transcribe(_audio(queue)):
                if update.is_final:
                    await self.final_transcript(voice_turn_id, update.text)
                    return
                await self.partial_transcript(voice_turn_id, update.text)
            await self.final_transcript(voice_turn_id, "")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._fail(voice_turn_id, type(error).__name__, str(error))
        finally:
            self._input_queues.pop(voice_turn_id, None)

    async def _conversation_to_speech(
        self,
        voice_session_id: UUID,
        voice_turn_id: UUID,
        ready: asyncio.Event,
    ) -> None:
        voice_session = await self._sessions.get(voice_session_id)
        text: _SpeechQueue = asyncio.Queue(8)
        synthesis = self._start_task(
            voice_turn_id,
            self._synthesize(voice_session_id, voice_turn_id, text),
        )
        text_started = False
        async with self._conversation_events.listen(
            voice_session.session_id
        ) as subscription:
            ready.set()
            try:
                while True:
                    event = await subscription.receive()
                    if event.type is ConversationEventType.CHAT_DELTA:
                        chunk = str(event.data["text"])
                        if not text_started and chunk.strip():
                            text_started = True
                            await self._publish_turn_event(
                                voice_turn_id,
                                VoiceEventType.ASSISTANT_TEXT_STARTED,
                                {},
                            )
                        await text.put(chunk)
                    elif event.type is ConversationEventType.TOOL_CALL_STARTED:
                        await text.put(_Flush.MARKER)
                        await self._publish_turn_event(
                            voice_turn_id,
                            VoiceEventType.ASSISTANT_TOOL_STARTED,
                            {"name": event.data["name"]},
                        )
                    elif event.type is ConversationEventType.TOOL_CALL_COMPLETED:
                        await self._publish_turn_event(
                            voice_turn_id,
                            VoiceEventType.ASSISTANT_TOOL_COMPLETED,
                            {"name": event.data["name"]},
                        )
                    elif event.type is ConversationEventType.CHAT_COMPLETED:
                        await text.put(None)
                    elif event.type is ConversationEventType.TURN_COMPLETED:
                        await synthesis
                        return
                    elif event.type is ConversationEventType.TURN_CANCELLED:
                        self._cancel_tasks(voice_turn_id, except_task=synthesis)
                        return
                    elif event.type is ConversationEventType.TURN_FAILED:
                        await self._fail(
                            voice_turn_id,
                            str(event.data.get("code", "conversation_failed")),
                            str(event.data.get("message", "Conversation turn failed")),
                        )
                        return
            finally:
                if not synthesis.done():
                    synthesis.cancel()
                await asyncio.gather(synthesis, return_exceptions=True)

    async def _synthesize(
        self,
        voice_session_id: UUID,
        voice_turn_id: UUID,
        text: _SpeechQueue,
    ) -> None:
        sequence = 0
        started = False
        segments = _SpeechSegments(text)
        while (segment := await segments.next()) is not None:
            async for chunk in self._text_to_speech.synthesize(segment):
                if not started:
                    await self._speech_started(voice_turn_id)
                    started = True
                voice_session, turn = await self._find_turn(voice_turn_id)
                sequence += 1
                await self._media.send_audio(
                    voice_session_id,
                    turn.index,
                    sequence,
                    time.time_ns() // 1_000_000,
                    chunk,
                )
        voice_session, turn = await self._find_turn(voice_turn_id)
        sequence += 1
        await self._media.send_audio(
            voice_session_id,
            turn.index,
            sequence,
            time.time_ns() // 1_000_000,
            b"",
            end=True,
        )
        lifecycle_sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.ASSISTANT_AUDIO_COMPLETED,
                voice_session.id,
                voice_session.session_id,
                {},
                voice_turn_id=turn.id,
                sequence=lifecycle_sequence,
            )
        )

    async def _speech_started(self, voice_turn_id: UUID) -> None:
        voice_session, turn = await self._find_turn(voice_turn_id)
        turn.start_speaking()
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.ASSISTANT_AUDIO_STARTED,
                voice_session.id,
                voice_session.session_id,
                {},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )

    async def _publish_turn_event(
        self,
        voice_turn_id: UUID,
        event_type: VoiceEventType,
        data: dict[str, object],
    ) -> None:
        voice_session, turn = await self._find_turn(voice_turn_id)
        sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                event_type,
                voice_session.id,
                voice_session.session_id,
                data,
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )

    async def _fail(self, voice_turn_id: UUID, code: str, message: str) -> None:
        voice_session, turn = await self._find_turn(voice_turn_id)
        if turn.status.terminal:
            return
        turn.fail(code, message)
        sequence = voice_session.next_sequence()
        self._cancel_tasks(voice_turn_id)
        async with self._repositories() as repository:
            await repository.save(voice_session)
        await self._events.publish_voice(
            VoiceEvent(
                VoiceEventType.TURN_FAILED,
                voice_session.id,
                voice_session.session_id,
                {"code": code, "message": message},
                voice_turn_id=turn.id,
                sequence=sequence,
            )
        )

    def _start_task(
        self,
        voice_turn_id: UUID,
        coroutine,
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine)
        tasks = self._tasks.setdefault(voice_turn_id, set())
        tasks.add(task)
        task.add_done_callback(
            lambda completed, turn_id=voice_turn_id: self._discard_task(
                turn_id,
                completed,
            )
        )
        return task

    def _discard_task(self, voice_turn_id: UUID, task: asyncio.Task[None]) -> None:
        tasks = self._tasks.get(voice_turn_id)
        if tasks is None:
            return
        tasks.discard(task)
        if not tasks:
            self._tasks.pop(voice_turn_id, None)

    def _cancel_tasks(
        self,
        voice_turn_id: UUID,
        *,
        except_task: asyncio.Task[None] | None = None,
    ) -> None:
        current = asyncio.current_task()
        for task in tuple(self._tasks.get(voice_turn_id, set())):
            if task is not current and task is not except_task:
                task.cancel()

    async def _find_turn(self, voice_turn_id: UUID) -> tuple:
        async with self._repositories() as repository:
            sessions = await repository.find_many()
        for voice_session in sessions:
            try:
                return voice_session, voice_session.get_turn(voice_turn_id)
            except VoiceTurnNotFoundError:
                pass
        raise VoiceTurnNotFoundError(voice_turn_id)


async def _audio(queue: asyncio.Queue[bytes | None]):
    while True:
        chunk = await queue.get()
        if chunk is None:
            return
        yield chunk


class _Flush(Enum):
    MARKER = auto()


class _SpeechSegments:
    """Splits a turn's text stream at flush markers so text spoken before a
    tool call is synthesized right away instead of at the end of the turn."""

    def __init__(self, queue: _SpeechQueue) -> None:
        self._queue = queue
        self._ended = False

    async def next(self) -> AsyncIterator[str] | None:
        while not self._ended:
            item = await self._queue.get()
            if item is None:
                self._ended = True
            elif isinstance(item, str) and item.strip():
                return self._rest(item)
        return None

    async def _rest(self, first: str) -> AsyncIterator[str]:
        yield first
        while True:
            item = await self._queue.get()
            if item is None:
                self._ended = True
                return
            if item is _Flush.MARKER:
                return
            yield item
