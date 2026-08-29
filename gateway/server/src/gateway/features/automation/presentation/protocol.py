from pyrpckit import feature

from gateway.features.automation.presentation.rpc_methods import AutomationRpcMethods

AUTOMATION_PROTOCOL = feature(
    "automation",
    handlers=(AutomationRpcMethods,),
)
