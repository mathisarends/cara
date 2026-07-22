import functools
from pathlib import Path

import numpy as np
import onnxruntime as ort

from cara.audio.ports import TurnDetector

_SAMPLE_RATE = 16_000
_CHUNK_SECONDS = 8
_MAX_SAMPLES = _SAMPLE_RATE * _CHUNK_SECONDS
_FFT_SIZE = 400
_HOP_LENGTH = 160
_MEL_FILTERS = 80
_MODEL_PATH = Path(__file__).with_name("models") / "smart_turn_v3_2_cpu.onnx"


class SmartTurnDetector(TurnDetector):
    """Local Smart Turn v3.2 endpoint detector backed by quantized ONNX."""

    def __init__(self, *, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        self._threshold = threshold
        self._session = _build_session(_MODEL_PATH)

    @property
    def sample_rate(self) -> int:
        return _SAMPLE_RATE

    def is_complete(self, utterance: bytes) -> bool:
        if len(utterance) % np.dtype(np.int16).itemsize:
            raise ValueError("Smart Turn expects complete int16 PCM samples")
        samples = np.frombuffer(utterance, dtype=np.int16).astype(np.float32) / 32768.0
        features = _whisper_log_mel_features(samples)
        probability = self._session.run(None, {"input_features": features})[0]
        return float(probability[0, 0]) >= self._threshold


def _build_session(model_path: Path) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def _whisper_log_mel_features(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1:
        raise ValueError("Smart Turn audio must be mono")
    if audio.size > _MAX_SAMPLES:
        audio = audio[-_MAX_SAMPLES:]
    elif audio.size < _MAX_SAMPLES:
        audio = np.pad(audio, (_MAX_SAMPLES - audio.size, 0))

    audio = (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)
    centered = np.pad(audio, (_FFT_SIZE // 2, _FFT_SIZE // 2), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(centered, _FFT_SIZE)[::_HOP_LENGTH]
    windowed = frames * _hann_window()
    spectrum = np.fft.rfft(windowed, n=_FFT_SIZE, axis=1)
    power = np.abs(spectrum).astype(np.float64) ** 2
    mel_spectrum = np.maximum(1e-10, _mel_filter_bank().T @ power.T)
    log_spectrum = np.log10(mel_spectrum)[:, :-1]
    log_spectrum = np.maximum(log_spectrum, log_spectrum.max() - 8.0)
    features = ((log_spectrum + 4.0) / 4.0).astype(np.float32)
    return features[np.newaxis, ...]


@functools.cache
def _hann_window() -> np.ndarray:
    return np.hanning(_FFT_SIZE + 1)[:-1]


@functools.cache
def _mel_filter_bank() -> np.ndarray:
    mel_min = _hertz_to_mel(0.0)
    mel_max = _hertz_to_mel(_SAMPLE_RATE / 2)
    mel_frequencies = np.linspace(mel_min, mel_max, _MEL_FILTERS + 2)
    filter_frequencies = _mel_to_hertz(mel_frequencies)
    fft_frequencies = np.linspace(0, _SAMPLE_RATE // 2, 1 + _FFT_SIZE // 2)

    frequency_differences = np.diff(filter_frequencies)
    slopes = filter_frequencies[np.newaxis, :] - fft_frequencies[:, np.newaxis]
    down_slopes = -slopes[:, :-2] / frequency_differences[:-1]
    up_slopes = slopes[:, 2:] / frequency_differences[1:]
    filters = np.maximum(0.0, np.minimum(down_slopes, up_slopes))

    energy_normalization = 2.0 / (filter_frequencies[2:] - filter_frequencies[:-2])
    return filters * energy_normalization[np.newaxis, :]


def _hertz_to_mel(frequency: float | np.ndarray) -> float | np.ndarray:
    minimum_log_hertz = 1_000.0
    minimum_log_mel = 15.0
    log_step = 27.0 / np.log(6.4)
    mels = 3.0 * frequency / 200.0
    if isinstance(frequency, np.ndarray):
        log_region = frequency >= minimum_log_hertz
        mels[log_region] = minimum_log_mel + np.log(frequency[log_region] / minimum_log_hertz) * log_step
    elif frequency >= minimum_log_hertz:
        mels = minimum_log_mel + np.log(frequency / minimum_log_hertz) * log_step
    return mels


def _mel_to_hertz(mels: np.ndarray) -> np.ndarray:
    minimum_log_hertz = 1_000.0
    minimum_log_mel = 15.0
    log_step = np.log(6.4) / 27.0
    frequencies = 200.0 * mels / 3.0
    log_region = mels >= minimum_log_mel
    frequencies[log_region] = minimum_log_hertz * np.exp(log_step * (mels[log_region] - minimum_log_mel))
    return frequencies
