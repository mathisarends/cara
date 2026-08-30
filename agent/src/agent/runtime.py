from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TurnFailure:
    error: Exception
