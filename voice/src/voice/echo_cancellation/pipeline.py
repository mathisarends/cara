import time

from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation.cancellers import NlmsEchoCanceller
from voice.echo_cancellation.devices import EchoCancellingInput, ReferenceTapOutput
from voice.echo_cancellation.ports import Clock, EchoCanceller
from voice.echo_cancellation.timeline import PlaybackTimeline


def wrap_with_echo_cancellation(
    input_device: AudioInput,
    output_device: AudioOutput,
    canceller: EchoCanceller | None = None,
    *,
    sample_rate: int | None = None,
    alignment_margin_s: float = 0.04,
    history_seconds: float = 2.0,
    clock: Clock = time.monotonic,
) -> tuple[AudioInput, AudioOutput]:
    if input_device.channels != 1:
        raise ValueError("Echo cancellation requires mono microphone input.")
    sample_rate = sample_rate or input_device.sample_rate
    if input_device.sample_rate != sample_rate:
        raise ValueError(
            "Echo cancellation sample rate must match the microphone sample rate."
        )

    timeline = PlaybackTimeline(
        sample_rate,
        history_seconds=history_seconds,
        clock=clock,
    )
    return (
        EchoCancellingInput(
            input_device,
            timeline,
            canceller or NlmsEchoCanceller(sample_rate),
            sample_rate=sample_rate,
            alignment_margin_s=alignment_margin_s,
            clock=clock,
        ),
        ReferenceTapOutput(output_device, timeline),
    )
