from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PromptAction:
    instruction: str

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("Automation instruction must not be empty")


@dataclass(frozen=True, slots=True)
class AutomationOrigin:
    created_from_turn_id: UUID
