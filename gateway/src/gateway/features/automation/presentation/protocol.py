from gateway.features.automation.presentation.rpc_methods import AutomationRpcMethods
from gateway.presentation.rpc import feature

AUTOMATION_PROTOCOL = feature(
    "automation",
    handlers=(AutomationRpcMethods,),
)
