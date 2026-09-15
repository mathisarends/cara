from fastapi_canon import Feature

from gateway.features.alarm.infrastructure import AlarmProvider
from gateway.features.alarm.presentation import alarm_module, alarm_router

feature = Feature(
    name="alarm",
    routers=(alarm_router,),
    providers=(AlarmProvider,),
)
rpc_module = alarm_module
