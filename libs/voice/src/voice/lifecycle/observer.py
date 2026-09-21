from abc import ABC, abstractmethod

from voice.lifecycle.events import VoiceLifecycleEvent


class VoiceLifecycleObserver(ABC):
    """Watches a voice session without taking part in its control flow."""

    @abstractmethod
    async def on_lifecycle_event(self, event: VoiceLifecycleEvent) -> None: ...
