from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation.cancellers import NlmsEchoCanceller
from voice.echo_cancellation.devices import EchoCancellingInput, ReferenceTapOutput
from voice.echo_cancellation.models import EchoCancellationSettings
from voice.echo_cancellation.ports import EchoCanceller
from voice.echo_cancellation.timeline import PlaybackTimeline


def wrap_with_echo_cancellation(
    input_device: AudioInput,
    output_device: AudioOutput,
    canceller: EchoCanceller | None = None,
    *,
    settings: EchoCancellationSettings | None = None,
) -> tuple[AudioInput, AudioOutput]:
    settings = settings or EchoCancellationSettings()
    if input_device.channels != 1:
        raise ValueError("Echo cancellation requires mono microphone input.")
    sample_rate = settings.sample_rate or input_device.sample_rate
    if input_device.sample_rate != sample_rate:
        raise ValueError(
            "Echo cancellation sample rate must match the microphone sample rate."
        )

    timeline = PlaybackTimeline(
        sample_rate,
        history_seconds=settings.history_seconds,
        clock=settings.clock,
    )
    return (
        EchoCancellingInput(
            input_device,
            timeline,
            canceller or NlmsEchoCanceller(sample_rate),
            sample_rate=sample_rate,
            alignment_margin_s=settings.alignment_margin_s,
            clock=settings.clock,
        ),
        ReferenceTapOutput(output_device, timeline),
    )
