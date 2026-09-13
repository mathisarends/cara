from gateway.features.automation.infrastructure import AutomationProvider
from gateway.features.automation.presentation.rpc.methods import automation_module
from gateway.presentation import Feature

feature = Feature(
    name="automation",
    providers=(AutomationProvider,),
    module=automation_module,
)
