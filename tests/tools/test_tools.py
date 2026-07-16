import asyncio
from typing import Annotated, Literal

from pydantic import Field

from cara.tools import ActionKind, ActionResult, EndSessionParams, Inject, ToolParams, Tools


class Greeting:
    def __init__(self, text: str) -> None:
        self.text = text


class SearchParams(ToolParams):
    query: str = Field(description="Search query")
    limit: int = 10
    tags: list[str] = Field(default_factory=list, min_length=1, max_length=3)


def test_default_end_session_tool_returns_farewell() -> None:
    tools = Tools()

    result = asyncio.run(
        tools.execute(
            "end_session",
            {"farewell": "Bis bald!", "status": "Ich beende die Sitzung..."},
        )
    )

    assert result == ActionResult.success("Bis bald!")


def test_default_end_session_tool_is_tagged_with_kind() -> None:
    tools = Tools()
    end_session = tools.get("end_session")

    assert end_session is not None
    assert end_session.param_model is EndSessionParams
    assert end_session.kind is ActionKind.END_SESSION


def test_action_decorator_registers_tool() -> None:
    tools = Tools()

    @tools.action(description="Echo a message.")
    async def echo(message: str) -> ActionResult:
        return ActionResult.success(message)

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == ActionResult.success("hi")
    assert tools.get("echo") is not None


def test_action_decorator_supports_pydantic_params() -> None:
    tools = Tools()

    @tools.action(params=SearchParams)
    async def search(params: SearchParams) -> ActionResult:
        return ActionResult.success(f"{params.query}:{params.limit}")

    result = asyncio.run(tools.execute("search", {"query": "songs"}))

    assert result == ActionResult.success("songs:10")


def test_to_schema_returns_openai_compatible_function_schema() -> None:
    tools = Tools()

    @tools.action(description="Pick a song.")
    async def pick_song(
        greeting: Inject[Greeting],
        title: Annotated[str, "Song title"],
        mood: Literal["calm", "bright"] = "calm",
    ) -> ActionResult:
        return ActionResult.success(f"{greeting.text}: {title} ({mood})")

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "pick_song")

    assert schema == {
        "type": "function",
        "function": {
            "name": "pick_song",
            "description": "Pick a song.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"description": "Song title", "type": "string"},
                    "mood": {"type": "string", "enum": ["calm", "bright"]},
                },
                "required": ["title"],
            },
        },
    }


def test_to_schema_uses_pydantic_param_model() -> None:
    tools = Tools()

    @tools.action(params=SearchParams)
    async def search(params: SearchParams) -> ActionResult:
        return ActionResult.success(params.query)

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "search")

    assert schema["function"]["parameters"] == {
        "type": "object",
        "properties": {
            "query": {"description": "Search query", "type": "string"},
            "limit": {"type": "integer", "default": 10},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
            },
        },
        "required": ["query"],
    }
