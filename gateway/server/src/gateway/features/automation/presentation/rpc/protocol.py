import pyrpckit as rpc

from gateway.features.automation.presentation.rpc.handler import AutomationRpcMethods

AUTOMATION_PROTOCOL = rpc.feature(
    "automation",
    handlers=(AutomationRpcMethods,),
)
