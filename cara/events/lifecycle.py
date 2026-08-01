from transitbus import Event


class SessionStarted(Event):
    """Emitted when a multi-turn voice session begins."""


class UserSpeechStarted(Event):
    """Emitted when voice activity is first detected for a user utterance."""


class UserSpeechEnded(Event):
    """Emitted when the recorder accepts the end of a user utterance."""


class AssistantSpeechStarted(Event):
    """Emitted immediately before the first assistant audio chunk is played."""


class AssistantInterrupted(Event):
    """Emitted when a repeated wake word interrupts an in-flight response."""


class SessionEnded(Event):
    """Emitted when a multi-turn voice session ends."""
