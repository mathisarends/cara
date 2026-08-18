import logging

from voice.acknowledgment.port import AcknowledgmentStrategy

logger = logging.getLogger(__name__)


class LoggingAcknowledgment(AcknowledgmentStrategy):
    """Logs the acknowledgment instead of playing it."""

    async def acknowledge(self, phrase: str) -> None:
        logger.info("Acknowledgment: %s", phrase)
