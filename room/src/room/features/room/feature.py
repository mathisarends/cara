from fastapi_canon import Feature

from room.features.room.infrastructure import RoomProvider

feature = Feature(
    name="room",
    providers=(RoomProvider,),
)
