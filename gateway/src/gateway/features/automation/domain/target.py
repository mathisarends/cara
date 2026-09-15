from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionTarget:
    session_id: UUID


type AutomationTarget = SessionTarget
