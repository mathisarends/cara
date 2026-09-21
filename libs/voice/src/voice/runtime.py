import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from dataclasses import dataclass, replace

from voice import backend
from voice.activation import (
    Activation,
    ActivationKind,
    ActivationSource,
    ListenActivation,
)
from voice.audio import AudioOutput, BufferedAudioInput
from voice.audio.input_uploader import TurnInputUploader
from voice.audio.playback import (
    PlaybackController,
    PlaybackFinished,
    PlaybackSignal,
    PlaybackStarted,
)
from voice.backend import (
    BackendEvent,
    BackendSessionState,
    BackendStreamEndedError,
    StartTurn,
    TurnAlreadyActiveError,
    TurnPhase,
    TurnRef,
    VoiceBackend,
)
from voice.barge_in import BargeInSignal, BargeInStrategy, NoBargeIn
from voice.integrations import VoiceIntegration, VoiceIntegrationContext
from voice.integrations.notifier import VoiceIntegrationNotifier
from voice.lifecycle import (
    AssistantSpeechCompleted,
    AssistantSpeechStarted,
    AssistantTextStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    SessionStarted,
    SessionStopped,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTurnStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
    VoiceConversationStarted,
    VoiceLifecycleEvent,
    VoiceLifecycleObserver,
    VoiceTurnEnded,
    VoiceTurnFailed,
    VoiceTurnInterrupted,
    VoiceTurnTimedOut,
    WakeWordDetected,
)
from voice.lifecycle.dispatcher import LifecycleDispatcher

logger = logging.getLogger(__name__)

_PRE_ROLL_SECONDS = 0.16


class VoiceRuntime:
    """Owns a running voice session's turn state and drives its control flow.

    Activation sources, the backend, barge-in and playback report to a single
    control loop, which alone changes the turn state. Audio bypasses the loop:
    the microphone streams through per-turn uploaders and the backend's audio
    through the playback controller.
    """

    def __init__(
        self,
        *,
        backend: VoiceBackend,
        audio_input: BufferedAudioInput,
        audio_output: AudioOutput,
        activation_sources: Iterable[ActivationSource] = (),
        barge_in: BargeInStrategy | None = None,
        integrations: Iterable[VoiceIntegration] = (),
        observers: Iterable[VoiceLifecycleObserver] = (),
        max_echo_confidence: float = 0.5,
        accept_activations: Callable[[], bool] | None = None,
    ) -> None:
        if audio_input.format.sample_rate != backend.input_format.sample_rate:
            raise ValueError(
                "Audio input sample rate does not match the negotiated backend format"
            )
        self._backend = backend
        self._audio_input = audio_input
        self._signals: asyncio.Queue[_Signal] = asyncio.Queue()
        self._playback = PlaybackController(
            audio_output,
            audio_format=backend.output_format,
            notify=self._signals.put_nowait,
        )
        self._activation_sources = tuple(activation_sources)
        self._barge_in = barge_in or NoBargeIn()
        self._integrations = VoiceIntegrationNotifier(integrations)
        self._lifecycle = LifecycleDispatcher((*observers, self._integrations))
        self._max_echo_confidence = max_echo_confidence
        self._accept_activations = accept_activations or (lambda: True)
        self._state: _TurnState = _Ready()
        self._upload: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._started = False
        self._stopped = False
        self._finished = asyncio.Event()
        self._startup_complete = asyncio.Event()
        self._startup_error: BaseException | None = None

    async def run(self) -> None:
        """Run until a source ends, the backend closes, or ``stop`` is called.

        Raises whatever failure ended the session.
        """
        if self._started:
            raise RuntimeError("A voice runtime can only run once.")
        self._started = True
        failure: BaseException | None = None
        try:
            await self._start()
            self._startup_complete.set()
            await self._run_control_loop()
        except BaseException as error:
            if not self._startup_complete.is_set():
                self._startup_error = error
                self._startup_complete.set()
            failure = error
            raise
        finally:
            await self._shutdown(failure)
            self._finished.set()

    async def wait_started(self) -> None:
        await self._startup_complete.wait()
        if self._startup_error is not None:
            raise self._startup_error

    async def stop(self) -> None:
        if not self._started:
            self._started = True
            await self._shutdown(None)
            return
        self._signals.put_nowait(_StopRequested())
        await self._finished.wait()

    async def _start(self) -> None:
        self._lifecycle.start()
        await self._integrations.start(
            VoiceIntegrationContext(audio_player=self._playback)
        )
        await self._audio_input.start()
        self._publish(SessionStarted())
        await self._restore(self._backend.initial_state)
        for source in self._activation_sources:
            self._supervise(
                f"{type(source).__name__} activations",
                self._pump_activations(source),
            )
        self._supervise("backend event stream", self._pump_backend_events())
        self._supervise("backend audio stream", self._pump_backend_audio())
        self._supervise("microphone capture", self._audio_input.wait_stopped())
        self._supervise("barge-in detection", self._pump_barge_in(), ends_session=False)

    async def _run_control_loop(self) -> None:
        while True:
            match await self._signals.get():
                case _ActivationReceived(activation=activation):
                    await self._on_activation(activation)
                case _BackendEventReceived(event=event):
                    await self._on_backend_event(event)
                case _BargeInDetected(signal=signal):
                    await self._on_barge_in(signal)
                case _InputUploadFailed(turn=turn, error=error):
                    await self._on_upload_failed(turn, error)
                case PlaybackStarted(turn=turn):
                    self._on_playback_started(turn)
                case PlaybackFinished(turn=turn, error=error):
                    await self._on_playback_finished(turn, error)
                case _StopRequested(error=None):
                    return
                case _StopRequested(error=error) if error is not None:
                    raise error

    async def _restore(self, state: BackendSessionState) -> None:
        active = state.active_turn
        if active is None:
            return
        turn = active.turn
        logger.info("Restoring voice turn %s (%s)", turn.id, active.phase)
        match active.phase:
            case TurnPhase.LISTENING:
                await self._begin_capture(turn)
            case TurnPhase.TRANSCRIBING:
                # The input already ended; its transcript completes the
                # user's part of the turn.
                self._state = _Capturing(turn, speech_detected=True)
                await self._playback.select(turn)
            case TurnPhase.WAITING_FOR_ASSISTANT | TurnPhase.SPEAKING:
                await self._await_assistant(turn)

    async def _on_activation(self, activation: Activation) -> None:
        await self._handle_activation(activation)
        detection = activation.detection
        if detection is not None:
            self._publish(
                WakeWordDetected(
                    name=detection.name,
                    score=detection.score,
                    sequence=detection.sequence,
                )
            )

    async def _handle_activation(self, activation: Activation) -> None:
        match self._state:
            case _Ready():
                await self._start_turn(activation)
                return
            case _WaitingForAssistant() | _Playing() as responding:
                signal = self._barge_in.interruption_for(activation)
                if signal is not None:
                    await self._interrupt(responding.turn, signal)
                    return
        logger.info(
            "Ignoring the %s activation: voice turn %s is still active",
            activation.kind,
            self._state_turn_id(),
        )

    async def _start_turn(self, activation: Activation) -> None:
        request = StartTurn(
            activation=activation.kind,
            pre_roll_sequence=activation.sequence,
        )
        try:
            started = await self._backend.start_turn(request)
        except TurnAlreadyActiveError:
            logger.warning(
                "The backend refused the %s activation: it already has an "
                "active voice turn",
                activation.kind,
            )
            return
        await self._begin_capture(
            started.turn,
            from_sequence=activation.sequence,
            end_after=activation.speech_start_timeout,
        )

    async def _begin_capture(
        self,
        turn: TurnRef,
        *,
        from_sequence: int | None = None,
        end_after: float | None = None,
    ) -> None:
        self._state = _Capturing(turn)
        await self._playback.select(turn)
        self._publish(UserTurnStarted(turn_id=turn.id))
        reader = await self._audio_input.open_reader(
            from_sequence=from_sequence,
            pre_roll_seconds=_PRE_ROLL_SECONDS,
        )
        uploader = TurnInputUploader(
            self._backend,
            turn,
            reader,
            max_echo_confidence=self._max_echo_confidence,
            end_after=end_after,
        )
        self._upload = self._spawn(
            self._upload_input(turn, uploader), name=f"voice-input-{turn.id}"
        )

    async def _await_assistant(self, turn: TurnRef) -> None:
        self._state = _WaitingForAssistant(turn)
        await self._playback.select(turn)
        self._publish(AssistantTurnStarted(turn_id=turn.id))

    async def _on_backend_event(self, event: BackendEvent) -> None:
        match event:
            case backend.ConversationStarted():
                self._publish(VoiceConversationStarted())
            case backend.ConversationCountdown(remaining_seconds=remaining):
                self._publish(
                    VoiceConversationInactivityCountdown(remaining_seconds=remaining)
                )
            case backend.ConversationEnded(reason=reason):
                self._publish(VoiceConversationEnded(reason=reason))
            case backend.TurnStarted(turn=turn, proactive=proactive):
                await self._on_turn_started(turn, proactive=proactive)
            case backend.TranscriptUpdated(turn=turn):
                self._on_user_speech(turn)
            case backend.TranscriptCompleted(turn=turn):
                await self._on_transcript_completed(turn)
            case backend.AssistantTextStarted(turn=turn):
                self._publish(AssistantTextStarted(turn_id=turn.id))
            case backend.AssistantToolStarted(turn=turn, name=name):
                self._publish(AssistantToolStarted(turn_id=turn.id, name=name))
            case backend.AssistantToolCompleted(turn=turn, name=name):
                self._publish(AssistantToolCompleted(turn_id=turn.id, name=name))
            case backend.TurnCompleted(turn=turn):
                await self._end_turn(turn)
            case backend.TurnDiscarded(turn=turn):
                if turn == self._active_turn:
                    self._publish(VoiceTurnTimedOut(turn_id=turn.id))
                await self._end_turn(turn)
            case backend.TurnFailed(turn=turn, message=message):
                if turn == self._active_turn:
                    self._publish(VoiceTurnFailed(turn_id=turn.id, message=message))
                await self._end_turn(turn)

    async def _on_turn_started(self, turn: TurnRef, *, proactive: bool) -> None:
        match self._state:
            case _Ready():
                logger.info(
                    "Voice turn %s started by the backend (%s)",
                    turn.id,
                    "proactive" if proactive else "listening",
                )
                if proactive:
                    await self._await_assistant(turn)
                else:
                    await self._begin_capture(turn)
            case _ if turn == self._active_turn:
                # Confirms a turn this runtime started itself.
                pass
            case _:
                logger.warning(
                    "The backend started voice turn %s while %s is still active here",
                    turn.id,
                    self._state_turn_id(),
                )

    def _on_user_speech(self, turn: TurnRef) -> None:
        # Transcription is what distinguishes speech from an open microphone,
        # so a follow-up turn only counts as speech once the backend hears it.
        match self._state:
            case _Capturing(speech_detected=False) as capturing if (
                capturing.turn == turn
            ):
                self._state = replace(capturing, speech_detected=True)
                self._publish(UserSpeechStarted(turn_id=turn.id))

    async def _on_transcript_completed(self, turn: TurnRef) -> None:
        capturing = self._state
        if not isinstance(capturing, _Capturing) or capturing.turn != turn:
            logger.debug("Ignoring the transcript of inactive voice turn %s", turn.id)
            return
        await self._stop_upload()
        if not capturing.speech_detected:
            self._publish(UserSpeechStarted(turn_id=turn.id))
        self._publish(UserSpeechEnded(turn_id=turn.id))
        await self._await_assistant(turn)

    async def _on_barge_in(self, signal: BargeInSignal) -> None:
        match self._state:
            case _WaitingForAssistant() | _Playing() as responding:
                await self._interrupt(responding.turn, signal)
            case _:
                # While the user holds the floor, their speech is the turn.
                logger.debug(
                    "Ignoring barge-in at sequence %d: the assistant is not responding",
                    signal.sequence,
                )

    async def _interrupt(self, turn: TurnRef, signal: BargeInSignal) -> None:
        logger.info(
            "Barge-in at sequence %d interrupts voice turn %s", signal.sequence, turn.id
        )
        await self._playback.interrupt()
        self._publish(VoiceTurnInterrupted(turn_id=turn.id))
        await self._backend.interrupt(turn, signal.sequence)
        await self._end_turn(turn)
        await self._start_turn(
            ListenActivation(sequence=signal.sequence, kind=ActivationKind.BARGE_IN)
        )

    async def _on_upload_failed(self, turn: TurnRef, error: Exception) -> None:
        if turn != self._active_turn:
            return
        logger.error(
            "Uploading the input of voice turn %s failed", turn.id, exc_info=error
        )
        await self._fail_turn(turn, error)

    def _on_playback_started(self, turn: TurnRef) -> None:
        match self._state:
            case _WaitingForAssistant() as waiting if waiting.turn == turn:
                self._state = _Playing(turn)
                self._publish(AssistantSpeechStarted(turn_id=turn.id))

    async def _on_playback_finished(
        self, turn: TurnRef, error: Exception | None
    ) -> None:
        if turn != self._active_turn:
            logger.info(
                "Not reporting playback of voice turn %s: the active turn is %s",
                turn.id,
                self._state_turn_id(),
            )
            return
        if error is not None:
            logger.error("Playing voice turn %s failed", turn.id, exc_info=error)
            await self._fail_turn(turn, error)
            return
        self._publish(AssistantSpeechCompleted(turn_id=turn.id))
        await self._backend.playback_completed(turn)

    async def _fail_turn(self, turn: TurnRef, error: Exception) -> None:
        # The backend would otherwise wait for this turn forever.
        self._publish(VoiceTurnFailed(turn_id=turn.id, message=str(error)))
        await self._backend.interrupt(turn, None)
        await self._end_turn(turn)

    async def _end_turn(self, turn: TurnRef) -> None:
        if turn != self._active_turn:
            logger.info(
                "Ignoring the end of voice turn %s: the active turn is %s",
                turn.id,
                self._state_turn_id(),
            )
            return
        await self._stop_upload()
        await self._playback.release(turn)
        self._state = _Ready()
        logger.info("Voice turn %s ended", turn.id)
        self._publish(VoiceTurnEnded(turn_id=turn.id))

    async def _upload_input(self, turn: TurnRef, uploader: TurnInputUploader) -> None:
        try:
            await uploader.run()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._signals.put_nowait(_InputUploadFailed(turn, error))

    async def _stop_upload(self) -> None:
        task, self._upload = self._upload, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _pump_activations(self, source: ActivationSource) -> None:
        async for activation in source.activations():
            if not self._accept_activations():
                logger.info("Ignoring voice activation while the room is not ready")
                continue
            self._signals.put_nowait(_ActivationReceived(activation))

    async def _pump_backend_events(self) -> None:
        async for event in self._backend.events():
            if isinstance(event, backend.SessionClosed):
                logger.info("The backend closed the voice session: %s", event.reason)
                return
            self._signals.put_nowait(_BackendEventReceived(event))
        raise BackendStreamEndedError("The backend event stream ended unexpectedly")

    async def _pump_backend_audio(self) -> None:
        async for audio in self._backend.output_audio():
            await self._playback.accept(audio)
        raise BackendStreamEndedError("The backend audio stream ended unexpectedly")

    async def _pump_barge_in(self) -> None:
        async for signal in self._barge_in.signals():
            self._signals.put_nowait(_BargeInDetected(signal))

    def _supervise(
        self,
        description: str,
        pump: Coroutine[None, None, None],
        *,
        ends_session: bool = True,
    ) -> None:
        self._spawn(
            self._run_pump(description, pump, ends_session=ends_session),
            name=f"voice-{description.lower().replace(' ', '-')}",
        )

    async def _run_pump(
        self,
        description: str,
        pump: Coroutine[None, None, None],
        *,
        ends_session: bool,
    ) -> None:
        try:
            await pump
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("The %s failed", description)
            self._signals.put_nowait(_StopRequested(error))
            return
        if ends_session:
            logger.info("The %s ended; stopping the voice session", description)
            self._signals.put_nowait(_StopRequested())

    def _spawn(
        self, coroutine: Coroutine[None, None, None], *, name: str
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _shutdown(self, failure: BaseException | None) -> None:
        if self._stopped:
            return
        self._stopped = True
        await _attempt_each(
            ("stop the session's tasks", self._cancel_tasks),
            ("release the active turn", lambda: self._release_active_turn(failure)),
            ("stop the lifecycle observers", self._stop_observers),
            ("stop playback", self._playback.stop),
            ("stop the microphone capture", self._audio_input.stop),
        )

    async def _cancel_tasks(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _release_active_turn(self, failure: BaseException | None) -> None:
        turn = self._active_turn
        if turn is None:
            return
        await self._stop_upload()
        if isinstance(failure, Exception):
            self._publish(VoiceTurnFailed(turn_id=turn.id, message=str(failure)))
        try:
            await self._backend.interrupt(turn, None)
        except Exception:
            logger.warning(
                "Could not interrupt voice turn %s while stopping",
                turn.id,
                exc_info=True,
            )
        await self._end_turn(turn)

    async def _stop_observers(self) -> None:
        self._publish(SessionStopped())
        await self._lifecycle.aclose()
        await self._integrations.stop()

    def _publish(self, event: VoiceLifecycleEvent) -> None:
        self._lifecycle.publish(event)

    @property
    def _active_turn(self) -> TurnRef | None:
        if isinstance(self._state, _Ready):
            return None
        return self._state.turn

    def _state_turn_id(self) -> object:
        turn = self._active_turn
        return None if turn is None else turn.id


async def _attempt_each(*steps: tuple[str, Callable[[], Awaitable[None]]]) -> None:
    """Run every cleanup step, even after an earlier one failed."""
    for description, step in steps:
        try:
            await step()
        except Exception:
            logger.exception("Could not %s", description)


@dataclass(frozen=True, slots=True)
class _Ready:
    pass


@dataclass(frozen=True, slots=True)
class _Capturing:
    """The user holds the floor and their audio streams to the backend."""

    turn: TurnRef
    speech_detected: bool = False


@dataclass(frozen=True, slots=True)
class _WaitingForAssistant:
    turn: TurnRef


@dataclass(frozen=True, slots=True)
class _Playing:
    turn: TurnRef


type _TurnState = _Ready | _Capturing | _WaitingForAssistant | _Playing


@dataclass(frozen=True, slots=True)
class _ActivationReceived:
    activation: Activation


@dataclass(frozen=True, slots=True)
class _BackendEventReceived:
    event: BackendEvent


@dataclass(frozen=True, slots=True)
class _BargeInDetected:
    signal: BargeInSignal


@dataclass(frozen=True, slots=True)
class _InputUploadFailed:
    turn: TurnRef
    error: Exception


@dataclass(frozen=True, slots=True)
class _StopRequested:
    error: Exception | None = None


type _Signal = (
    _ActivationReceived
    | _BackendEventReceived
    | _BargeInDetected
    | _InputUploadFailed
    | PlaybackSignal
    | _StopRequested
)
