from pathlib import Path

import numpy as np
import onnxruntime as ort

from cara.audio.ports import VoiceActivityDetector

_SAMPLE_RATE = 16_000
_FRAME_SAMPLES = 512
_CONTEXT_SAMPLES = 64
_MODEL_PATH = Path(__file__).with_name("models") / "silero_vad.onnx"


class SileroVoiceActivityDetector(VoiceActivityDetector):
    """Streaming Silero VAD backed by the bundled ONNX model."""

    def __init__(self, *, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        self._threshold = threshold
        self._session = _build_session(_MODEL_PATH)
        self._state: np.ndarray
        self._context: np.ndarray
        self.reset()

    @property
    def sample_rate(self) -> int:
        return _SAMPLE_RATE

    @property
    def frame_samples(self) -> int:
        return _FRAME_SAMPLES

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, _CONTEXT_SAMPLES), dtype=np.float32)

    def is_speech(self, frame: bytes) -> bool:
        expected_bytes = _FRAME_SAMPLES * np.dtype(np.int16).itemsize
        if len(frame) != expected_bytes:
            raise ValueError(f"Silero VAD expects {expected_bytes} PCM bytes, got {len(frame)}")

        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        model_input = np.concatenate((self._context, samples.reshape(1, -1)), axis=1)
        probability, self._state = self._session.run(
            None,
            {
                "input": model_input,
                "state": self._state,
                "sr": np.array(_SAMPLE_RATE, dtype=np.int64),
            },
        )
        self._context = model_input[:, -_CONTEXT_SAMPLES:]
        return float(probability[0, 0]) >= self._threshold


def _build_session(model_path: Path) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
