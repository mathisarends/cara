class TurnAlreadyActiveError(RuntimeError):
    """The backend refused to start a turn because another one is active."""


class BackendStreamEndedError(ConnectionError):
    """A backend stream ended while the session still depended on it."""
