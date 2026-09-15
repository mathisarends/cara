from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptAction:
    instruction: str

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("Automation instruction must not be empty")
