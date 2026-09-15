from fastapi_canon import Error, ErrorRegistry

from gateway.features.automation.domain import AutomationNotFoundError
from gateway.features.conversation.presentation import SESSION_NOT_FOUND

AUTOMATION_NOT_FOUND = Error(
    AutomationNotFoundError,
    status=404,
    code="automation_not_found",
    title="Automation not found",
    detail=str,
)

AUTOMATION_ERRORS = ErrorRegistry(
    name="automation",
    # Creating an automation resolves its session target through conversation.
    errors=[AUTOMATION_NOT_FOUND, SESSION_NOT_FOUND],
)
