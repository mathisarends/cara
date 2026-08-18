from pathlib import Path

from llmify import AssistantMessage, Function, ToolCall, ToolResultMessage

from agent.messages import MessageManager
from agent.prompt import SystemPrompt


def _manager(root: Path) -> MessageManager:
    return MessageManager(SystemPrompt(root=root, system_prompt="System"))


def test_messages_are_appended_in_order(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    manager.add_user("one")
    manager.add_assistant("two")
    manager.add_user("three")

    assert [message.content for message in manager.to_llm_messages()] == [
        "System",
        "one",
        "two",
        "three",
    ]


def test_tool_round_pairs_calls_with_their_results(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    tool_call = ToolCall(id="call-1", function=Function(name="lookup", arguments="{}"))

    manager.add_user("Wie wird das Wetter?")
    manager.add_tool_round(
        "",
        [tool_call],
        [ToolResultMessage(tool_call_id="call-1", content="22 Grad.")],
    )

    llm_messages = manager.to_llm_messages()
    assistant_call, tool_result = llm_messages[2], llm_messages[3]
    assert isinstance(assistant_call, AssistantMessage)
    assert assistant_call.tool_calls[0].id == "call-1"
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.content == "22 Grad."


def test_multiple_tool_rounds_are_stored_as_individual_pairs(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    first = ToolCall(id="call-1", function=Function(name="lookup", arguments="{}"))
    second = ToolCall(id="call-2", function=Function(name="read_file", arguments="{}"))

    manager.add_tool_round(
        "", [first], [ToolResultMessage(tool_call_id="call-1", content="a")]
    )
    manager.add_tool_round(
        "", [second], [ToolResultMessage(tool_call_id="call-2", content="b")]
    )

    llm_messages = manager.to_llm_messages()
    assert isinstance(llm_messages[1], AssistantMessage)
    assert llm_messages[1].tool_calls[0].id == "call-1"
    assert isinstance(llm_messages[2], ToolResultMessage)
    assert llm_messages[2].tool_call_id == "call-1"
    assert isinstance(llm_messages[3], AssistantMessage)
    assert llm_messages[3].tool_calls[0].id == "call-2"
    assert isinstance(llm_messages[4], ToolResultMessage)
    assert llm_messages[4].tool_call_id == "call-2"
