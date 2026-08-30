from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation.alignment import ReferenceAligner
from voice.echo_cancellation.cancellers import NlmsEchoCanceller
from voice.echo_cancellation.devices import EchoCancellingInput, ReferenceTapOutput
from voice.echo_cancellation.models import EchoCancellationSettings
from voice.echo_cancellation.ports import EchoCanceller
from voice.echo_cancellation.reference import PlaybackReference


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

    reference = PlaybackReference(
        sample_rate,
        history_seconds=settings.reference_history_seconds,
    )
    alignment = settings.alignment
    aligner = ReferenceAligner(
        reference,
        window_seconds=alignment.window_seconds,
        interval_seconds=alignment.interval_seconds,
        tracking_seconds=alignment.tracking_seconds,
        filter_headroom_seconds=alignment.filter_headroom_seconds,
        min_correlation=alignment.min_correlation,
        min_level_dbfs=alignment.min_level_dbfs,
        analysis_sample_rate=alignment.analysis_sample_rate,
    )
    return (
        EchoCancellingInput(
            input_device,
            aligner,
            canceller or NlmsEchoCanceller(sample_rate),
        ),
        ReferenceTapOutput(output_device, reference),
    )
