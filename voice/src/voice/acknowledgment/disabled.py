from voice.acknowledgment.port import AcknowledgmentStrategy


class NoAcknowledgment(AcknowledgmentStrategy):
    """Leaves the gap between user speech and the assistant's answer silent."""

    async def acknowledge(self, phrase: str) -> None:
        return
