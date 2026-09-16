from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceDelivery:
    room: str

    def __post_init__(self) -> None:
        if not self.room.strip():
            raise ValueError("Voice delivery room must not be empty")
