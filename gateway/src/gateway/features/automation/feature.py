from fastapi_canon import Feature

from gateway.features.automation.infrastructure import AutomationProvider
from gateway.features.automation.presentation.rpc.methods import automation_module

feature = Feature(
    name="automation",
    providers=(AutomationProvider,),
)
rpc_module = automation_module
