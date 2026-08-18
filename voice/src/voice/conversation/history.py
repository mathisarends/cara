from .models import ConversationMessage


class ConversationHistory:
    """Stores the ordered messages of a voice conversation."""

    def __init__(self) -> None:
        self._turns: list[ConversationMessage] = []

    @property
    def turns(self) -> tuple[ConversationMessage, ...]:
        return tuple(self._turns)

    def add(self, message: ConversationMessage) -> None:
        self._turns.append(message)
