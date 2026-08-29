from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChannelRef:
    name: str
    account_id: str | None = None
