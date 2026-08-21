from gateway.features.automation.presentation.rpc_methods import AutomationRpcMethods
from gateway.presentation.rpc import rpc_feature

AUTOMATION_PROTOCOL = rpc_feature(
    "automation",
    handler=AutomationRpcMethods,
)
