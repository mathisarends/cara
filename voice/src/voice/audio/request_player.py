from voice.audio.ports import AudioPlayback
from voice.events import AudioPlaybackRequested
from voice.events.bus import EventBus


class EventAudioPlayer(AudioPlayback):
    """Routes clip playback through the voice event system."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def play(self, audio: bytes) -> None:
        await self._event_bus.request(AudioPlaybackRequested(audio=audio))
