import logging

_BRIGHT_CYAN = "\x1b[96m"
_BRIGHT_GREEN = "\x1b[92m"
_RESET = "\x1b[0m"


def _log_user_transcript(logger: logging.Logger, transcript: str) -> None:
    logger.info("%s[heard] %s%s", _BRIGHT_CYAN, transcript, _RESET)


def _log_spoken_text(logger: logging.Logger, text: str) -> None:
    logger.info("%s[says] %s%s", _BRIGHT_GREEN, text, _RESET)
