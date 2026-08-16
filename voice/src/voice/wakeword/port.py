from collections.abc import AsyncIterator
from typing import Protocol

from voice.pipeline.models import WakeWordDetection


class WakeWordSource(Protocol):
    @property
    def phrase(self) -> str: ...

    def detections(self) -> AsyncIterator[WakeWordDetection]: ...
