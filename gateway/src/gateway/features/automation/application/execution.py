from datetime import datetime

from gateway.features.automation.application.ports import AutomationActionExecutor
from gateway.features.automation.domain import Automation


class AutomationExecution:
    def __init__(self, executor: AutomationActionExecutor) -> None:
        self._executor = executor

    async def execute(
        self,
        automation: Automation,
        *,
        scheduled_for: datetime,
    ) -> None:
        await self._executor.execute(
            automation.id,
            automation.target,
            automation.action,
            scheduled_for,
        )
