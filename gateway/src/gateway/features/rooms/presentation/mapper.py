from gateway.features.rooms.domain import Room
from gateway.features.rooms.presentation.schemas import DeviceResponse, RoomResponse


def to_room_response(room: Room) -> RoomResponse:
    return RoomResponse(
        room_id=room.room_id,
        display_name=room.display_name,
        online=room.online,
        functions=room.functions,
        state=room.state,
        volume=room.volume,
        client_version=room.client_version,
        devices=tuple(
            DeviceResponse(
                device_id=device.device_id,
                kind=device.kind,
                capabilities=device.capabilities,
                status=device.status,
            )
            for device in room.devices
        ),
    )
