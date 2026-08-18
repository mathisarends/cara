from unittest.mock import Mock

import pytest

from voice.vad import silero as silero_module


@pytest.fixture
def silero_backend(monkeypatch) -> Mock:
    backend = Mock()
    monkeypatch.setattr(silero_module, "_SileroDetector", lambda: backend)
    return backend
