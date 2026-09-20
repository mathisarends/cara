from uuid import uuid4

from gateway.features.rooms.domain import (
    Capability,
    Device,
    DeviceKind,
    DeviceStatus,
    Room,
    RoomFunction,
)


def test_functions_are_derived_from_available_devices_while_online() -> None:
    room = Room(uuid4(), "Schlafzimmer")
    microphone = Device(
        "microphone",
        DeviceKind.MICROPHONE,
        frozenset({Capability.AUDIO_INPUT}),
    )
    speaker = Device(
        "speaker",
        DeviceKind.SPEAKER,
        frozenset({Capability.AUDIO_OUTPUT, Capability.MEDIA_PLAYBACK}),
    )
    light = Device("light", DeviceKind.LIGHT, frozenset({Capability.LIGHT}))

    room.register((microphone, speaker, light), "1.0.0")
    room.connected()

    assert room.functions == frozenset(
        {
            RoomFunction.CONVERSATION,
            RoomFunction.ANNOUNCE,
            RoomFunction.MUSIC,
            RoomFunction.LIGHT,
        }
    )

    speaker.report_status(DeviceStatus.UNAVAILABLE)

    assert room.functions == frozenset({RoomFunction.LIGHT})


def test_offline_room_exposes_no_functions() -> None:
    room = Room(uuid4(), "Schlafzimmer")
    speaker = Device(
        "speaker",
        DeviceKind.SPEAKER,
        frozenset({Capability.AUDIO_OUTPUT}),
    )
    room.register((speaker,), "1.0.0")

    assert room.functions == frozenset()
