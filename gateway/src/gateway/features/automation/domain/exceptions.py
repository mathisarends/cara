class AutomationNotFoundError(Exception):
    def __init__(self, automation_id: str) -> None:
        super().__init__(f"Automation {automation_id!r} not found")
