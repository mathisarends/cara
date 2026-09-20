from fastapi_canon import Feature

from room.features.room.infrastructure import RoomProvider
from room.features.room.presentation import room_router

feature = Feature(
    name="room",
    routers=(room_router,),
    providers=(RoomProvider,),
)
