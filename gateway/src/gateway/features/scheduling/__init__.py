from gateway.presentation import Feature

from .infrastructure import SchedulingProvider

feature = Feature(name="scheduling", providers=[SchedulingProvider])

__all__ = ["feature"]
