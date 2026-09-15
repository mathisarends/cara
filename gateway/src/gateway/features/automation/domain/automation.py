import uuid
from datetime import UTC, datetime
from typing import Self

from gateway.features.automation.domain.action import AutomationOrigin, PromptAction
from gateway.features.automation.domain.errors import AutomationNotFoundError
from gateway.features.automation.domain.schedule import AutomationSchedule
from gateway.features.automation.domain.target import AutomationTarget


class Automation:
    def __init__(
        self,
        id: str,
        created_at: datetime,
        owner_id: str,
        target: AutomationTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
        next_run_at: datetime | None = None,
    ) -> None:
        if not id.strip():
            raise ValueError("Automation id must not be empty")
        if not owner_id.strip():
            raise ValueError("Automation owner id must not be empty")
        self._id = id
        self._created_at = created_at
        self._owner_id = owner_id
        self._target = target
        self._schedule = schedule
        self._action = action
        self._origin = origin
        self._name = name
        self._next_run_at = next_run_at

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        target: AutomationTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Self:
        return cls(
            id=uuid.uuid4().hex,
            created_at=datetime.now(UTC),
            owner_id=owner_id,
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
    def origin(self) -> AutomationOrigin:
        return self._origin

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def next_run_at(self) -> datetime | None:
        return self._next_run_at

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
        origin: AutomationOrigin,
        name: str | None,
    ) -> Self:
        self._schedule = schedule
        self._action = action
        self._origin = origin
        self._name = name
        return self
