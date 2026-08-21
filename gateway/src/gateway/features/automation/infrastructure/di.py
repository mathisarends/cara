from dishka import Provider, Scope, provide

from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import AutomationEnvelope
from scheduler import Scheduler


class AutomationProvider(Provider):
    scope = Scope.APP

    @provide
    def service(
        self,
        scheduler: Scheduler[AutomationEnvelope],
    ) -> AutomationService:
        return AutomationService(scheduler)
