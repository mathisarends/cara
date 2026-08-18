from voice.observer import Observer, ObserverContext
from voice.playback.ducking import DuckingStrategy
from voice.playback.strategy import PlaybackStrategy


class SonosPlaybackObserver(Observer):
    """Applies a playback strategy while a voice interaction is active."""

    def __init__(
        self,
        *,
        strategy: PlaybackStrategy | None = None,
    ) -> None:
        self._strategy = strategy if strategy is not None else DuckingStrategy()

    async def prepare(self, context: ObserverContext) -> None:
        await self._strategy.prepare()

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        await self._strategy.activate(reason="wake word detected")

    async def on_user_turn_started(self) -> None:
        await self._strategy.activate(reason="user turn started")

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        await self._strategy.deactivate(reason="user inactivity timeout")

    async def on_agent_error(self, turn_id: int, message: str) -> None:
        await self._strategy.deactivate(reason=f"voice turn {turn_id} failed")

    async def on_voice_turn_timed_out(self, turn_id: int) -> None:
        await self._strategy.deactivate(reason=f"voice turn {turn_id} timed out")

    async def on_agent_stopped(self) -> None:
        try:
            await self._strategy.deactivate(reason="voice agent stopped")
        finally:
            await self._strategy.close()
