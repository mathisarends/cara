from cara.tools.middleware.base import ToolMiddleware
from cara.tools.middleware.call_log import CallLoggingMiddleware
from cara.tools.middleware.content_size import ContentSizeMiddleware
from cara.tools.middleware.errors import ErrorBoundaryMiddleware
from cara.tools.middleware.path_policy import PathPolicyMiddleware
from cara.tools.middleware.result_limit import ResultLimitMiddleware


def default_tool_middlewares() -> tuple[ToolMiddleware, ...]:
    return (
        CallLoggingMiddleware(),
        ErrorBoundaryMiddleware(),
        ResultLimitMiddleware(),
        PathPolicyMiddleware(),
        ContentSizeMiddleware(),
    )
