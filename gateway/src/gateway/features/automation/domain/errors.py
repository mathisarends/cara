from uuid import UUID


class AutomationNotFoundError(Exception):
    def __init__(self, automation_id: UUID) -> None:
        super().__init__(f"Automation {automation_id} not found")
