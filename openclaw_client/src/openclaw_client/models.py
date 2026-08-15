from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

PROTOCOL_VERSION = 4


class _GatewayModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class OperatorScope(StrEnum):
    READ = "operator.read"
    WRITE = "operator.write"


class GatewayClientInfo(_GatewayModel):
    id: Literal["gateway-client"] = "gateway-client"
    version: str = "0.1.0"
    mode: Literal["backend"] = "backend"


class GatewayAuth(_GatewayModel):
    token: str | None = None
    password: str | None = None
    device_token: str | None = None


class ErrorShape(_GatewayModel):
    code: str
    message: str
    details: Any | None = None
    retryable: bool | None = None


class RequestFrame(_GatewayModel):
    type: Literal["req"] = "req"
    id: str = Field(default_factory=lambda: str(uuid4()))
    method: str
    params: Any | None = None


class ResponseFrame(_GatewayModel):
    type: Literal["res"]
    id: str
    ok: bool
    payload: Any | None = None
    error: ErrorShape | None = None


class EventFrame(_GatewayModel):
    type: Literal["event"]
    event: str
    payload: Any | None = None
    seq: int | None = None


class GatewayServer(_GatewayModel):
    version: str
    conn_id: str


class HelloOk(_GatewayModel):
    type: Literal["hello-ok"]
    protocol: int
    server: GatewayServer


class SessionsCreateResult(_GatewayModel):
    ok: Literal[True]
    key: str
    session_id: str | None = None
    run_started: bool | None = None
    run_id: str | None = None


class ChatSendStatus(StrEnum):
    STARTED = "started"
    OK = "ok"
    ERROR = "error"


class ChatSendAck(_GatewayModel):
    run_id: str
    status: ChatSendStatus
    summary: str | None = None


class ChatRunStartupPhase(StrEnum):
    PREPARING_WORKSPACE = "preparing_workspace"
    PROVISIONING_ENVIRONMENT = "provisioning_environment"
    PREPARING_CONTEXT = "preparing_context"
    STARTING_MODEL = "starting_model"


class ChatStatusEvent(_GatewayModel):
    run_id: str
    session_key: str
    agent_id: str | None = None
    seq: int
    state: Literal["status"]
    phase: ChatRunStartupPhase


class ChatDeltaEvent(_GatewayModel):
    run_id: str
    session_key: str
    agent_id: str | None = None
    seq: int
    state: Literal["delta"]
    message: Any | None = None
    delta_text: str
    replace: bool | None = None


class ChatFinalEvent(_GatewayModel):
    run_id: str
    session_key: str
    agent_id: str | None = None
    seq: int
    state: Literal["final"]
    message: Any | None = None
    stop_reason: str | None = None


class ChatAbortedEvent(_GatewayModel):
    run_id: str
    session_key: str
    agent_id: str | None = None
    seq: int
    state: Literal["aborted"]
    message: Any | None = None
    error_message: str | None = None


class ChatErrorEvent(_GatewayModel):
    run_id: str
    session_key: str
    agent_id: str | None = None
    seq: int
    state: Literal["error"]
    message: Any | None = None
    error_message: str | None = None


type ChatEvent = (
    ChatStatusEvent
    | ChatDeltaEvent
    | ChatFinalEvent
    | ChatAbortedEvent
    | ChatErrorEvent
)


class TalkEventMode(StrEnum):
    REALTIME = "realtime"
    STT_TTS = "stt-tts"
    TRANSCRIPTION = "transcription"


class TalkEventTransport(StrEnum):
    WEBRTC = "webrtc"
    PROVIDER_WEBSOCKET = "provider-websocket"
    GATEWAY_RELAY = "gateway-relay"
    MANAGED_ROOM = "managed-room"


class TalkEventBrain(StrEnum):
    AGENT_CONSULT = "agent-consult"
    DIRECT_TOOLS = "direct-tools"
    NONE = "none"


class TalkEventType(StrEnum):
    SESSION_STARTED = "session.started"
    SESSION_READY = "session.ready"
    SESSION_CLOSED = "session.closed"
    SESSION_ERROR = "session.error"
    SESSION_REPLACED = "session.replaced"
    TURN_STARTED = "turn.started"
    TURN_ENDED = "turn.ended"
    TURN_CANCELLED = "turn.cancelled"
    CAPTURE_STARTED = "capture.started"
    CAPTURE_STOPPED = "capture.stopped"
    CAPTURE_CANCELLED = "capture.cancelled"
    CAPTURE_ONCE = "capture.once"
    INPUT_AUDIO_DELTA = "input.audio.delta"
    INPUT_AUDIO_COMMITTED = "input.audio.committed"
    TRANSCRIPT_DELTA = "transcript.delta"
    TRANSCRIPT_DONE = "transcript.done"
    OUTPUT_TEXT_DELTA = "output.text.delta"
    OUTPUT_TEXT_DONE = "output.text.done"
    OUTPUT_AUDIO_STARTED = "output.audio.started"
    OUTPUT_AUDIO_DELTA = "output.audio.delta"
    OUTPUT_AUDIO_DONE = "output.audio.done"
    TOOL_CALL = "tool.call"
    TOOL_PROGRESS = "tool.progress"
    TOOL_RESULT = "tool.result"
    TOOL_ERROR = "tool.error"
    USAGE_METRICS = "usage.metrics"


class TalkEvent(_GatewayModel):
    id: str
    type: TalkEventType
    session_id: str
    turn_id: str | None = None
    seq: int
    timestamp: str
    mode: TalkEventMode
    transport: TalkEventTransport
    brain: TalkEventBrain
    final: bool | None = None
    call_id: str | None = None
    item_id: str | None = None
    payload: Any = None


class GatewayEvent(_GatewayModel):
    event: str
    payload: Any | None = None
