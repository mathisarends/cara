import uuid
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from gateway.features.automation.domain.action import PromptAction
from gateway.features.automation.domain.errors import AutomationNotFoundError
from gateway.features.automation.domain.schedule import AutomationSchedule
from gateway.features.automation.domain.target import AutomationTarget


class Automation:
    def __init__(
        self,
        id: UUID,
        created_at: datetime,
        owner_id: str,
        target: AutomationTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        next_run_at: datetime,
        name: str | None = None,
    ) -> None:
        if not owner_id.strip():
            raise ValueError("Automation owner id must not be empty")
        self._id = id
        self._created_at = created_at
        self._owner_id = owner_id
        self._target = target
        self._schedule = schedule
        self._action = action
        self._next_run_at = next_run_at
        self._name = name

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        target: AutomationTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        next_run_at: datetime,
        name: str | None = None,
    ) -> Self:
        return cls(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            owner_id=owner_id,
            target=target,
            schedule=schedule,
            action=action,
            next_run_at=next_run_at,
            name=name,
        )

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def target(self) -> AutomationTarget:
        return self._target

    @property
    def schedule(self) -> AutomationSchedule:
        return self._schedule

    @property
    def action(self) -> PromptAction:
        return self._action

    @property
    def next_run_at(self) -> datetime:
        return self._next_run_at

    @property
    def name(self) -> str | None:
        return self._name

    def is_owned_by(self, owner_id: str) -> bool:
        return self._owner_id == owner_id

    def require_owner(self, owner_id: str) -> None:
        if not self.is_owned_by(owner_id):
            raise AutomationNotFoundError(self._id)

    def update(
        self,
        *,
        schedule: AutomationSchedule,
        action: PromptAction,
        name: str | None,
        next_run_at: datetime,
    ) -> Self:
        self._schedule = schedule
        self._action = action
        self._name = name
        self._next_run_at = next_run_at
        return self

    def reschedule(self, next_run_at: datetime) -> None:
        self._next_run_at = next_run_at
