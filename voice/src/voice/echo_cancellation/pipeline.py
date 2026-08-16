import time

from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation.cancellers import NlmsEchoCanceller
from voice.echo_cancellation.devices import EchoCancellingInput, ReferenceTapOutput
from voice.echo_cancellation.ports import Clock, EchoCanceller
from voice.echo_cancellation.timeline import PlaybackTimeline


class EchoCancellation:
    def __init__(
        self,
        canceller: EchoCanceller | None = None,
        *,
        sample_rate: int = 24000,
        alignment_margin_s: float = 0.04,
        history_seconds: float = 2.0,
        clock: Clock = time.monotonic,
    ):
        self._canceller = canceller or NlmsEchoCanceller(sample_rate)
        self._sample_rate = sample_rate
        self._alignment_margin_s = alignment_margin_s
        self._history_seconds = history_seconds
        self._clock = clock
        self._wrapped = False

    def wrap(
        self, input_device: AudioInput, output_device: AudioOutput
    ) -> tuple[AudioInput, AudioOutput]:
        if self._wrapped:
            raise RuntimeError(
                "EchoCancellation holds filter state for a single device pair - "
                "create a new instance per pair."
            )
        self._wrapped = True

        timeline = PlaybackTimeline(
            self._sample_rate,
            history_seconds=self._history_seconds,
            clock=self._clock,
        )
        return (
            EchoCancellingInput(
                input_device,
                timeline,
                self._canceller,
                sample_rate=self._sample_rate,
                alignment_margin_s=self._alignment_margin_s,
                clock=self._clock,
            ),
            ReferenceTapOutput(output_device, timeline),
        )
