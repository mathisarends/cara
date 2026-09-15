import uuid
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from gateway.features.automation.domain.action import (
    AutomationOrigin,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.domain.errors import AutomationNotFoundError
from gateway.features.automation.domain.schedule import AutomationSchedule


class Automation:
    def __init__(
        self,
        id: str,
        created_at: datetime,
        target: SessionTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
        next_run_at: datetime | None = None,
    ) -> None:
        if not id.strip():
            raise ValueError("Automation id must not be empty")
        self._id = id
        self._created_at = created_at
        self._target = target
        self._schedule = schedule
        self._action = action
        self._origin = origin
        self._name = name
        self._next_run_at = next_run_at

    @classmethod
    def create_for_session(
        cls,
        *,
        target: SessionTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Self:
        return cls(
            id=uuid.uuid4().hex,
            created_at=datetime.now(UTC),
            target=target,
            schedule=schedule,
            action=action,
            origin=origin,
            name=name,
        )

    @property
    def id(self) -> str:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def target(self) -> SessionTarget:
        return self._target

    @property
    def schedule(self) -> AutomationSchedule:
        return self._schedule

    @property
    def action(self) -> PromptAction:
        return self._action

    @property
    def origin(self) -> AutomationOrigin:
        return self._origin

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def next_run_at(self) -> datetime | None:
        return self._next_run_at

    def belongs_to_session(self, session_id: UUID) -> bool:
        return self._target.session_id == session_id

    def require_session(self, session_id: UUID) -> None:
        if not self.belongs_to_session(session_id):
            raise AutomationNotFoundError(self._id)

    def update(
        self,
        *,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None,
    ) -> Self:
        self._schedule = schedule
        self._action = action
        self._origin = origin
        self._name = name
        return self
