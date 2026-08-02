from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from agenttoolkit import Skills
from llmify import AssistantMessage, Function, ToolCall, ToolResultMessage

from cara.memory import MemoryStore
from cara.messages import MessageManager, RuntimeContext, SystemPrompt


def _tool_call() -> ToolCall:
    return ToolCall(id="call-1", function=Function(name="load_skill", arguments="{}"))


def _empty_memory(root: Path) -> MemoryStore:
    """A store over a directory without memory files, so nothing is injected."""
    return MemoryStore(root=root)


def _fixed_context() -> RuntimeContext:
    return RuntimeContext(
        location_name="Berlin",
        timezone="Europe/Berlin",
        clock=lambda: datetime(2026, 7, 21, 14, 30, tzinfo=ZoneInfo("Europe/Berlin")),
    )


def _skills(root: Path, name: str = "pdf", description: str = "Read PDFs.") -> Skills:
    directory = root / name
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nInstructions.\n",
        encoding="utf-8",
    )
    return Skills.from_local_dir(root)


def test_message_manager_builds_llm_messages_with_system_prompt(tmp_path: Path) -> None:
    messages = MessageManager(system_prompt="System", memory=_empty_memory(tmp_path))

    messages.add_user("Hi")
    messages.add_assistant("Hallo")

    llm_messages = messages.to_llm_messages()

    assert llm_messages[0].content == "System"
    assert llm_messages[1].content == "Hi"
    assert llm_messages[2].content == "Hallo"


def test_message_manager_retains_complete_history(tmp_path: Path) -> None:
    messages = MessageManager(system_prompt="System", memory=_empty_memory(tmp_path))

    messages.add_user("one")
    messages.add_assistant("two")
    messages.add_user("three")

    llm_messages = messages.to_llm_messages()

    assert [message.content for message in llm_messages] == ["System", "one", "two", "three"]


def test_tool_result_lands_in_context_paired_with_its_call(tmp_path: Path) -> None:
    messages = MessageManager(system_prompt="System", memory=_empty_memory(tmp_path))

    messages.add_user("Read this PDF")
    messages.add_tool_call(_tool_call())
    messages.add_tool_result("call-1", "Use the bundled parser.")
    messages.add_assistant("Mache ich.")

    llm_messages = messages.to_llm_messages()

    assistant_call, tool_result = llm_messages[2], llm_messages[3]
    assert isinstance(assistant_call, AssistantMessage)
    assert assistant_call.tool_calls[0].id == "call-1"
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.content == "Use the bundled parser."


def test_multiple_tools_are_stored_as_individual_call_result_pairs(tmp_path: Path) -> None:
    messages = MessageManager(system_prompt="System", memory=_empty_memory(tmp_path))
    first = _tool_call()
    second = ToolCall(id="call-2", function=Function(name="read_file", arguments="{}"))

    messages.add_tool_call(first)
    messages.add_tool_result(first.id, "skill instructions")
    messages.add_tool_call(second)
    messages.add_tool_result(second.id, "file contents")

    llm_messages = messages.to_llm_messages()
    assert isinstance(llm_messages[1], AssistantMessage)
    assert llm_messages[1].tool_calls[0].id == "call-1"
    assert isinstance(llm_messages[2], ToolResultMessage)
    assert llm_messages[2].tool_call_id == "call-1"
    assert isinstance(llm_messages[3], AssistantMessage)
    assert llm_messages[3].tool_calls[0].id == "call-2"
    assert isinstance(llm_messages[4], ToolResultMessage)
    assert llm_messages[4].tool_call_id == "call-2"


def test_available_skills_are_appended_to_the_system_prompt(tmp_path: Path) -> None:
    skills = _skills(tmp_path)
    messages = MessageManager(system_prompt="System", skills=skills, memory=_empty_memory(tmp_path))

    rendered = messages.to_llm_messages()[0].content

    assert rendered == (
        "System\n\n<available_skills>\n"
        "<skill>\n<name>pdf</name>\n<description>Read PDFs.</description>\n</skill>\n"
        "</available_skills>"
    )


def test_empty_skills_leaves_the_system_prompt_untouched(tmp_path: Path) -> None:
    messages = MessageManager(
        system_prompt="System",
        skills=Skills.from_local_dir(tmp_path),
        memory=_empty_memory(tmp_path),
    )

    assert messages.to_llm_messages()[0].content == "System"


def test_runtime_context_renders_location_and_local_time() -> None:
    assert _fixed_context().render() == (
        "Aktueller Standort: Berlin\nAktuelle lokale Zeit: Dienstag, 21. Juli 2026, 14:30 Uhr"
    )


def test_runtime_context_is_wrapped_in_a_context_block(tmp_path: Path) -> None:
    messages = MessageManager(system_prompt="System", context=_fixed_context(), memory=_empty_memory(tmp_path))

    rendered = messages.to_llm_messages()[0].content

    assert rendered == (
        "System\n\n<context>\n"
        "Aktueller Standort: Berlin\nAktuelle lokale Zeit: Dienstag, 21. Juli 2026, 14:30 Uhr"
        "\n</context>"
    )


def test_context_precedes_available_skills_in_the_system_prompt(tmp_path: Path) -> None:
    skills = _skills(tmp_path, "weather", "Wetter ansagen.")
    messages = MessageManager(
        system_prompt="System",
        skills=skills,
        context=_fixed_context(),
        memory=_empty_memory(tmp_path),
    )

    rendered = messages.to_llm_messages()[0].content

    assert rendered.index("<context>") < rendered.index("<available_skills>")


def test_system_prompt_reads_default_markdown() -> None:
    prompt = SystemPrompt().render()

    assert "<memory>" in prompt


def test_system_prompt_can_extend_default_prompt() -> None:
    prompt = SystemPrompt(extend_system_prompt="Nutze Tools sparsam.").render()

    assert "<memory>" in prompt
    assert prompt.endswith("Nutze Tools sparsam.")


def test_system_prompt_can_override_default_prompt() -> None:
    prompt = SystemPrompt(override_system_prompt="Nur JSON.").render()

    assert prompt == "Nur JSON."


def test_system_prompt_rejects_extend_and_override_together() -> None:
    with pytest.raises(ValueError):
        SystemPrompt(
            override_system_prompt="Override",
            extend_system_prompt="Extend",
        )
