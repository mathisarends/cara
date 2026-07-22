import asyncio
import functools
import io
import logging
import math
import threading
import time
import wave
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from cara.audio.microphone import MicrophoneStream
from cara.audio.ports import SpeechRecorder, TurnDetector, VoiceActivityDetector
from cara.audio.turn_detection import SmartTurnDetector
from cara.audio.vad import SileroVoiceActivityDetector

logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 2
_PREROLL_SECONDS = 0.5


@dataclass(frozen=True)
class MicrophoneInputSettings:
    candidate_silence_seconds: float = 0.8
    fallback_silence_seconds: float = 6.0
    min_record_seconds: float = 0.4
    max_record_seconds: float = 90.0

    def __post_init__(self) -> None:
        if self.candidate_silence_seconds <= 0:
            raise ValueError("candidate_silence_seconds must be positive")
        if self.fallback_silence_seconds < self.candidate_silence_seconds:
            raise ValueError("fallback_silence_seconds must not be shorter than candidate_silence_seconds")
        if self.min_record_seconds < 0:
            raise ValueError("min_record_seconds must not be negative")
        if self.max_record_seconds <= self.candidate_silence_seconds:
            raise ValueError("max_record_seconds must be longer than candidate_silence_seconds")


class MicrophoneRecorder(SpeechRecorder):
    """Records one user utterance from a shared microphone stream into a WAV file."""

    def __init__(
        self,
        microphone: MicrophoneStream,
        config: MicrophoneInputSettings | None = None,
        *,
        vad: VoiceActivityDetector | None = None,
        turn_detector: TurnDetector | None = None,
    ) -> None:
        self._microphone = microphone
        self._config = config or MicrophoneInputSettings()
        self._vad = vad or SileroVoiceActivityDetector()
        self._turn_detector = turn_detector or SmartTurnDetector()
        self._validate_audio_format()

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
    ) -> bytes | None:
        loop = asyncio.get_running_loop()
        cancelled = threading.Event()
        recording = loop.run_in_executor(
            None,
            functools.partial(
                self._record_until_silence_sync,
                initial_silence_timeout=initial_silence_timeout,
                cancel=cancelled,
                ready=ready,
            ),
        )
        try:
            return await asyncio.shield(recording)
        except asyncio.CancelledError:
            cancelled.set()
            await asyncio.shield(recording)
            raise

    def _record_until_silence_sync(
        self,
        *,
        initial_silence_timeout: float | None = None,
        cancel: threading.Event | None = None,
        ready: threading.Event | None = None,
    ) -> bytes | None:
        config = self._config
        mic = self._microphone
        rate = mic.rate
        chunk = self._vad.frame_samples

        frames: list[bytes] = []
        preroll: deque[bytes] = deque(maxlen=max(1, math.ceil(_PREROLL_SECONDS * rate / chunk)))
        started_at = time.monotonic()
        voice_started = False
        voice_chunks = 0
        silent_chunks = 0
        candidate_silent_chunks = max(1, math.ceil(config.candidate_silence_seconds * rate / chunk))
        fallback_silent_chunks = max(1, math.ceil(config.fallback_silence_seconds * rate / chunk))
        minimum_recorded_chunks = math.ceil(config.min_record_seconds * rate / chunk)
        maximum_recorded_chunks = math.ceil(config.max_record_seconds * rate / chunk)
        turn_check: Future[bool] | None = None
        turn_check_invalidated = False
        candidate_checked = False

        self._vad.reset()
        logger.info("Recording user utterance...")
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="cara-turn-detection") as turn_executor:
            while True:
                if cancel is not None and cancel.is_set():
                    logger.info("Recording cancelled.")
                    return None
                pcm = mic.read(chunk)
                is_speech = self._vad.is_speech(pcm)

                # Before speech begins, keep only a short pre-roll so the onset
                # of the first word is never clipped. Detection remains active
                # while the wake earcon is playing.
                if not voice_started:
                    preroll.append(pcm)
                    if is_speech:
                        voice_started = True
                        voice_chunks = 1
                        frames.extend(preroll)
                        preroll.clear()
                    elif (
                        initial_silence_timeout is not None and time.monotonic() - started_at >= initial_silence_timeout
                    ):
                        logger.info("No speech detected within %.1fs.", initial_silence_timeout)
                        return None
                    continue

                frames.append(pcm)
                voice_chunks += 1

                # End-of-utterance detection stays suspended until ``ready``, so
                # acoustic bleed from the earcon cannot finish the recording.
                armed = ready is None or ready.is_set()
                if not armed or voice_chunks < minimum_recorded_chunks:
                    silent_chunks = 0
                elif is_speech:
                    silent_chunks = 0
                    candidate_checked = False
                    if turn_check is not None:
                        turn_check_invalidated = True
                else:
                    silent_chunks += 1

                # Inference happens beside microphone capture. If speech resumes
                # before it finishes, its answer is stale and the complete turn
                # is checked again at the next pause.
                if turn_check is not None and turn_check.done():
                    complete = turn_check.result()
                    turn_check = None
                    if not turn_check_invalidated:
                        candidate_checked = True
                        if complete:
                            logger.info("Smart Turn detected a complete utterance.")
                            break

                if silent_chunks >= candidate_silent_chunks and turn_check is None and not candidate_checked:
                    utterance = b"".join(frames)
                    turn_check = turn_executor.submit(self._turn_detector.is_complete, utterance)
                    turn_check_invalidated = False

                if silent_chunks >= fallback_silent_chunks:
                    logger.info(
                        "Ending recording after %.1fs of silence (Smart Turn fallback).",
                        config.fallback_silence_seconds,
                    )
                    break
                if voice_chunks >= maximum_recorded_chunks:
                    logger.warning("Recording reached the %.1fs runaway limit.", config.max_record_seconds)
                    break

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(mic.channels)
            wav.setsampwidth(_SAMPLE_WIDTH)
            wav.setframerate(rate)
            wav.writeframes(b"".join(frames))

        audio = buffer.getvalue()
        logger.info("Recorded utterance (%d bytes).", len(audio))
        return audio

    def _validate_audio_format(self) -> None:
        mic = self._microphone
        if mic.channels != 1:
            raise ValueError("Voice and turn detection require mono microphone audio")
        if mic.rate != self._vad.sample_rate or mic.rate != self._turn_detector.sample_rate:
            raise ValueError(
                "Voice and turn detection require matching sample rates "
                f"(microphone={mic.rate}, vad={self._vad.sample_rate}, turn={self._turn_detector.sample_rate})"
            )
