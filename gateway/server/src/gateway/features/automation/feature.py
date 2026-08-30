from gateway.features.automation.infrastructure import AutomationProvider
from gateway.features.automation.presentation import AUTOMATION_PROTOCOL
from gateway.presentation import Feature

feature = Feature(
    name="automation",
    providers=(AutomationProvider,),
    protocol=AUTOMATION_PROTOCOL,
)
