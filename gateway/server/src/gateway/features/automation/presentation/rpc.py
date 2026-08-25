from enum import StrEnum


class AutomationRpcMethod(StrEnum):
    LIST = "automation.list"
    GET = "automation.get"
    CREATE = "automation.create"
    UPDATE = "automation.update"
    DELETE = "automation.delete"
