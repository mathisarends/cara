from typing import NotRequired, TypedDict


class FunctionSchema(TypedDict):
    name: str
    parameters: dict
    description: NotRequired[str]


class ToolSchema(TypedDict):
    type: str
    function: FunctionSchema