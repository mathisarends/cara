import logging
from dataclasses import fields
from uuid import UUID

from voice.lifecycle.events import VoiceLifecycleEvent
from voice.lifecycle.observer import VoiceLifecycleObserver

logger = logging.getLogger(__name__)

_MAX_VALUE_LENGTH = 60


class LifecycleTrace(VoiceLifecycleObserver):
    """Logs every lifecycle event at DEBUG in the order the session reached it."""

    async def on_lifecycle_event(self, event: VoiceLifecycleEvent) -> None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("%s", _describe(event))


def _describe(event: VoiceLifecycleEvent) -> str:
    rendered = ", ".join(
        f"{field.name}={_render(getattr(event, field.name))}" for field in fields(event)
    )
    return f"{type(event).__name__}({rendered})"


def _render(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)[:8]
    rendered = repr(value)
    if len(rendered) > _MAX_VALUE_LENGTH:
        return f"{rendered[:_MAX_VALUE_LENGTH]}..."
    return rendered
