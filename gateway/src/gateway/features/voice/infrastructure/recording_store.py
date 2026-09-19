from uuid import UUID

from gateway.features.voice.application import VoiceRecordingStore
from gateway.platform.storage import ContentType, ObjectStorage


class ObjectStorageVoiceRecordingStore(VoiceRecordingStore):
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    async def save_turn(
        self,
        voice_session_id: UUID,
        voice_turn_index: int,
        audio: bytes,
    ) -> None:
        await self._storage.upload_bytes(
            f"{_folder(voice_session_id)}/{voice_turn_index:06d}.mp3",
            audio,
            ContentType.MPEG,
        )

    async def load(self, voice_session_id: UUID) -> bytes | None:
        segments = sorted(
            await self._storage.list_files(_folder(voice_session_id)),
            key=lambda segment: segment.path,
        )
        if not segments:
            return None
        return b"".join(
            [await self._storage.get_bytes(segment.path) for segment in segments]
        )


def _folder(voice_session_id: UUID) -> str:
    return f"voice-recordings/{voice_session_id}"
