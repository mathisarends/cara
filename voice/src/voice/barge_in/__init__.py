"""Interruption detection strategies for active assistant responses."""

from .ports import BargeIn
from .wakeword import WakeWordBargeIn

__all__ = ["BargeIn", "WakeWordBargeIn"]
