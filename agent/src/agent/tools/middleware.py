import logging
import time

from agenttoolkit import ToolCall, ToolMiddleware
from agenttoolkit.builtins import CommandError, WorkspaceError
from agenttoolkit.tools.middleware import ToolHandler
from pydantic import ValidationError

logger = logging.getLogger(__name__)

_OUTPUT_SNIPPET_LENGTH = 300


class ToolError(Exception):
    """An expected tool failure that should be returned to the model."""


class ToolFailure(str):
    """A model-visible tool result that is also identifiable as a failure."""


_EXPECTED_TOOL_ERRORS = (
    ToolError,
    ValidationError,
    CommandError,
    WorkspaceError,
    FileNotFoundError,
    IsADirectoryError,
    NotADirectoryError,
    PermissionError,
)


class ToolResultMiddleware(ToolMiddleware):
    """Log one outcome per tool call and preserve traces for real crashes."""

    async def __call__(self, call: ToolCall, next: ToolHandler) -> object:
        logger.info("[tool] %s called with arguments: %r", call.name, call.raw_args)
        started = time.perf_counter()
        try:
            result = await next(call)
        except Exception as error:
            if not _is_expected_tool_error(error):
                logger.exception(
                    "[tool] FAIL %s crashed (%.0f ms); arguments: %r",
                    call.name,
                    _elapsed_ms(started),
                    call.raw_args,
                )
                raise

            elapsed_ms = _elapsed_ms(started)
            logger.warning(
                "[tool] FAIL %s failed (%.0f ms): %s; arguments: %r",
                call.name,
                elapsed_ms,
                _single_line(error),
                call.raw_args,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            return ToolFailure(f"Tool failed: {error}")

        elapsed_ms = _elapsed_ms(started)
        logger.info(
            "[tool] OK %s finished (%.0f ms); arguments: %r",
            call.name,
            elapsed_ms,
            call.raw_args,
        )
        logger.debug("[tool] %s output: %s", call.name, _output_snippet(result))
        return result


def _is_expected_tool_error(error: Exception) -> bool:
    return isinstance(error, _EXPECTED_TOOL_ERRORS) or type(error) is LookupError


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _single_line(value: object) -> str:
    return " ".join(str(value).split())


def _output_snippet(result: object) -> str:
    rendered = str(result)
    if len(rendered) > _OUTPUT_SNIPPET_LENGTH:
        rendered = f"{rendered[:_OUTPUT_SNIPPET_LENGTH]}…"
    return repr(rendered)
