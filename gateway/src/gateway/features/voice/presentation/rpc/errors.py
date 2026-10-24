from fastapi_rpckit import RpcErrorBinding

from gateway.features.voice.domain import (
    InvalidVoiceTurnTransitionError,
    MediaNotConnectedError,
    VoiceSessionClosedError,
    VoiceTurnAlreadyActiveError,
)

VOICE_TURN_ALREADY_ACTIVE = RpcErrorBinding(
    VoiceTurnAlreadyActiveError,
    code="voice_turn_already_active",
    rpc_code=-32011,
    message=str,
)
MEDIA_NOT_CONNECTED = RpcErrorBinding(
    MediaNotConnectedError,
    code="media_not_connected",
    rpc_code=-32012,
    message=str,
)
VOICE_SESSION_CLOSED = RpcErrorBinding(
    VoiceSessionClosedError,
    code="voice_session_closed",
    rpc_code=-32015,
    message=str,
)
INVALID_VOICE_TURN_TRANSITION = RpcErrorBinding(
    InvalidVoiceTurnTransitionError,
    code="invalid_voice_turn_transition",
    rpc_code=-32016,
    message=str,
)
