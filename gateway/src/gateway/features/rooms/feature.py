from fastapi_canon import Feature

from gateway.features.rooms.infrastructure.provider import RoomProvider
from gateway.features.rooms.presentation import room_router

feature = Feature(
    name="rooms",
    routers=(room_router,),
    providers=(RoomProvider,),
)
