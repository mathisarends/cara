from uuid import UUID


class VoiceSessionNotFoundError(Exception):
    def __init__(self, voice_session_id: UUID) -> None:
        super().__init__(f"Voice session {voice_session_id} was not found")


class VoiceTurnNotFoundError(Exception):
    def __init__(self, voice_turn_id: UUID) -> None:
        super().__init__(f"Voice turn {voice_turn_id} was not found")


class VoiceSessionAlreadyOpenError(Exception):
    def __init__(self, device_id: str, voice_session_id: UUID) -> None:
        self.voice_session_id = voice_session_id
        super().__init__(
            f"Device {device_id!r} already has open voice session {voice_session_id}"
        )


class VoiceSessionClosedError(Exception):
    pass


class VoiceTurnAlreadyActiveError(Exception):
    pass


class InvalidVoiceTurnTransitionError(Exception):
    pass


class MediaNotConnectedError(Exception):
    pass


class NotMediaOwnerError(Exception):
    pass
