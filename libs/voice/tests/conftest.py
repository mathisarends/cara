from collections.abc import Callable

import numpy as np
import pytest


@pytest.fixture
def pcm() -> Callable[..., bytes]:
    def encode(*samples: int) -> bytes:
        return np.asarray(samples, dtype="<i2").tobytes()

    return encode
