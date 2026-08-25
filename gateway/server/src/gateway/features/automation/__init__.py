from gateway.presentation import Feature

from .infrastructure import AutomationProvider
from .presentation import AUTOMATION_PROTOCOL

feature = Feature(
    name="automation",
    providers=[AutomationProvider],
    protocol=AUTOMATION_PROTOCOL,
)

__all__ = ["feature"]
