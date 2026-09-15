from fastapi_canon import Feature

from gateway.features.automation.infrastructure import AutomationProvider
from gateway.features.automation.presentation import (
    automation_module,
    automation_router,
)

feature = Feature(
    name="automation",
    routers=(automation_router,),
    providers=(AutomationProvider,),
)
rpc_module = automation_module
