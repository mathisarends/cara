import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Self

_VERSION = 1
_HEADER = struct.Struct("!BBIQQI")


class MediaFrameKind(IntEnum):
    INPUT_PCM = 1
    INPUT_END = 2
    OUTPUT_PCM = 3
    OUTPUT_END = 4


@dataclass(frozen=True, slots=True)
class MediaFrame:
    kind: MediaFrameKind
    voice_turn_index: int
    sequence: int
    timestamp_ms: int
    payload: bytes = b""

    def encode(self) -> bytes:
        header = _HEADER.pack(
            _VERSION,
            self.kind,
            self.voice_turn_index,
            self.sequence,
            self.timestamp_ms,
            len(self.payload),
        )
        return header + self.payload

    @classmethod
    def decode(cls, data: bytes) -> Self:
        if len(data) < _HEADER.size:
            raise ValueError("Media frame is shorter than its header")
        version, kind, turn_index, sequence, timestamp_ms, payload_length = (
            _HEADER.unpack_from(data)
        )
        if version != _VERSION:
            raise ValueError(f"Unsupported media frame version {version}")
        payload = data[_HEADER.size :]
        if len(payload) != payload_length:
            raise ValueError("Media frame payload length does not match its header")
        frame_kind = MediaFrameKind(kind)
        if (
            frame_kind in {MediaFrameKind.INPUT_END, MediaFrameKind.OUTPUT_END}
            and payload
        ):
            raise ValueError("Media end frames cannot carry a payload")
        return cls(frame_kind, turn_index, sequence, timestamp_ms, payload)
