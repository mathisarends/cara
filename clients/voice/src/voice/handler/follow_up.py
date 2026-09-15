import asyncio
import logging
import time

from pydantic import BaseModel, ConfigDict, Field

from voice.activation import ActivationKind
from voice.events import (
    AssistantPlaybackCompleted,
    FollowUpCountdown,
    FollowUpTimedOut,
    SessionEnded,
    UserSpeechStarted,
    VoiceTurnTimedOut,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnRequested

logger = logging.getLogger(__name__)


class FollowUpSettings(BaseModel):
    """Timing for the wake-word-free follow-up window and its countdown."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    window_seconds: float = Field(default=5.0, gt=0.0)
    countdown_seconds: int = Field(default=3, ge=0)


class FollowUpHandler:
    """Keeps the conversation open for one further turn without a wake word."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        settings: FollowUpSettings | None = None,
    ) -> None:
        settings = settings or FollowUpSettings()
        self._event_bus = event_bus
        self._window_seconds = settings.window_seconds
        self._countdown_seconds = settings.countdown_seconds
        self._armed = False
        self._window_open = False
        self._countdown: asyncio.Task[None] | None = None

        event_bus.on(AssistantPlaybackCompleted, self._on_response_completed)
        event_bus.on(VoiceTurnEnded, self._on_turn_ended)
        event_bus.on(UserSpeechStarted, self._on_user_speech_started)
        event_bus.on(VoiceTurnTimedOut, self._on_turn_timed_out)
        event_bus.on(SessionEnded, self._on_session_ended)

    def close(self) -> None:
        self._armed = False
        self._close_window()

    async def _on_response_completed(self, _: AssistantPlaybackCompleted) -> None:
        self._armed = True

    async def _on_turn_ended(self, _: VoiceTurnEnded) -> None:
        if not self._armed:
            return
        self._armed = False
        await self._open_window()

    async def _on_user_speech_started(self, _: UserSpeechStarted) -> None:
        self._close_window()

    async def _on_turn_timed_out(self, _: VoiceTurnTimedOut) -> None:
        if not self._window_open:
            return
        self._close_window()
        logger.debug(
            "Follow-up window expired after %.1fs without speech", self._window_seconds
        )
        await self._event_bus.dispatch(
            FollowUpTimedOut(timeout_seconds=self._window_seconds)
        )

    async def _on_session_ended(self, _: SessionEnded) -> None:
        self.close()

    async def _open_window(self) -> None:
        self._window_open = True
        logger.debug("Opening follow-up window for %.1fs", self._window_seconds)
        await self._event_bus.request(
            VoiceTurnRequested(
                speech_start_timeout=self._window_seconds,
                activation=ActivationKind.FOLLOW_UP,
            )
        )
        self._countdown = asyncio.create_task(
            self._count_down(), name="voice-follow-up-countdown"
        )

    def _close_window(self) -> None:
        self._window_open = False
        countdown, self._countdown = self._countdown, None
        if countdown is not None:
            countdown.cancel()

    async def _count_down(self) -> None:
        deadline = time.monotonic() + self._window_seconds
        first_tick = min(self._countdown_seconds, int(self._window_seconds))
        for remaining in range(first_tick, 0, -1):
            await asyncio.sleep(max(deadline - remaining - time.monotonic(), 0.0))
            await self._event_bus.dispatch(
                FollowUpCountdown(remaining_seconds=remaining)
            )
