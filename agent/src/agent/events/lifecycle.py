from transitbus import Event


class SessionStarted(Event):
    """Emitted when a text or voice session begins."""


class UserTurnStarted(Event):
    """Emitted when an input channel starts waiting for the user."""


class AssistantTurnStarted(Event):
    """Emitted when the model starts working on a user turn."""


class ToolCallStarted(Event):
    """Emitted immediately before the assistant invokes a tool."""

    tool_name: str


class ToolCallFinished(Event):
    """Emitted when a tool invocation finishes or is interrupted."""

    tool_name: str


class UserSpeechStarted(Event):
    """Emitted when voice activity is first detected for a user utterance."""


class UserSpeechEnded(Event):
    """Emitted when the recorder accepts the end of a user utterance."""


class AssistantSpeechStarted(Event):
    """Emitted immediately before the first assistant audio chunk is played."""


class SessionEnded(Event):
    """Emitted when a text or voice session ends."""
