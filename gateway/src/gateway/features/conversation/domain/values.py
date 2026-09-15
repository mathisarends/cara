from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class ChannelRef:
    name: str


class SortOrder(StrEnum):
    ASCENDING = "asc"
    DESCENDING = "desc"
