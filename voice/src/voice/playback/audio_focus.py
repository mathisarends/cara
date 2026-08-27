from voice.observer import Observer, ObserverContext
from voice.playback.policy import SonosAudioFocusPolicy


class SonosAudioFocusObserver(Observer):
    """Keeps Sonos playback from competing with a voice interaction."""

    def __init__(
        self,
        *,
        policy: SonosAudioFocusPolicy,
    ) -> None:
        self._policy = policy

    async def prepare(self, context: ObserverContext) -> None:
        await self._policy.prepare()

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        await self._policy.activate(reason="wake word detected")

    async def on_user_turn_started(self) -> None:
        await self._policy.activate(reason="user turn started")

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        await self._policy.deactivate(reason="user inactivity timeout")

    async def on_agent_error(self, turn_id: int, message: str) -> None:
        await self._policy.deactivate(reason=f"voice turn {turn_id} failed")

    async def on_voice_turn_timed_out(self, turn_id: int) -> None:
        await self._policy.deactivate(reason=f"voice turn {turn_id} timed out")

    async def on_channel_stopped(self) -> None:
        await self._policy.deactivate(reason="voice channel stopped")
