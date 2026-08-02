from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from agenttoolkit import Skills
from llmify import AssistantMessage, Function, ToolCall, ToolResultMessage

from cara.prompt import Conversation, RuntimeContext, SystemPromptComposer


def _tool_call() -> ToolCall:
    return ToolCall(id="call-1", function=Function(name="load_skill", arguments="{}"))


def _composer(root: Path, **kwargs: object) -> SystemPromptComposer:
    return SystemPromptComposer(root=root, system_prompt="System", **kwargs)


def _conversation(root: Path) -> Conversation:
    return Conversation(system_prompt=_composer(root))


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


def test_conversation_builds_llm_messages_with_system_prompt(tmp_path: Path) -> None:
    conversation = _conversation(tmp_path)

    conversation.add_user("Hi")
    conversation.add_assistant("Hallo")

    llm_messages = conversation.to_llm_messages()

    assert llm_messages[0].content == "System"
    assert llm_messages[1].content == "Hi"
    assert llm_messages[2].content == "Hallo"


def test_conversation_retains_complete_history(tmp_path: Path) -> None:
    conversation = _conversation(tmp_path)

    conversation.add_user("one")
    conversation.add_assistant("two")
    conversation.add_user("three")

    llm_messages = conversation.to_llm_messages()

    assert [message.content for message in llm_messages] == ["System", "one", "two", "three"]


def test_tool_result_lands_in_context_paired_with_its_call(tmp_path: Path) -> None:
    conversation = _conversation(tmp_path)

    conversation.add_user("Read this PDF")
    conversation.add_tool_call(_tool_call())
    conversation.add_tool_result("call-1", "Use the bundled parser.")
    conversation.add_assistant("Mache ich.")

    llm_messages = conversation.to_llm_messages()

    assistant_call, tool_result = llm_messages[2], llm_messages[3]
    assert isinstance(assistant_call, AssistantMessage)
    assert assistant_call.tool_calls[0].id == "call-1"
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.content == "Use the bundled parser."


def test_multiple_tools_are_stored_as_individual_call_result_pairs(tmp_path: Path) -> None:
    conversation = _conversation(tmp_path)
    first = _tool_call()
    second = ToolCall(id="call-2", function=Function(name="read_file", arguments="{}"))

    conversation.add_tool_call(first)
    conversation.add_tool_result(first.id, "skill instructions")
    conversation.add_tool_call(second)
    conversation.add_tool_result(second.id, "file contents")

    llm_messages = conversation.to_llm_messages()
    assert isinstance(llm_messages[1], AssistantMessage)
    assert llm_messages[1].tool_calls[0].id == "call-1"
    assert isinstance(llm_messages[2], ToolResultMessage)
    assert llm_messages[2].tool_call_id == "call-1"
    assert isinstance(llm_messages[3], AssistantMessage)
    assert llm_messages[3].tool_calls[0].id == "call-2"
    assert isinstance(llm_messages[4], ToolResultMessage)
    assert llm_messages[4].tool_call_id == "call-2"


def test_available_skills_are_appended_to_the_system_prompt(tmp_path: Path) -> None:
    rendered = _composer(tmp_path, skills=_skills(tmp_path)).render()

    assert rendered == (
        "System\n\n<available_skills>\n"
        "<skill>\n<name>pdf</name>\n<description>Read PDFs.</description>\n</skill>\n"
        "</available_skills>"
    )


def test_empty_skills_leaves_the_system_prompt_untouched(tmp_path: Path) -> None:
    composer = _composer(tmp_path, skills=Skills.from_local_dir(tmp_path))

    assert composer.render() == "System"


def test_runtime_context_renders_location_and_local_time() -> None:
    assert _fixed_context().render() == (
        "Aktueller Standort: Berlin\nAktuelle lokale Zeit: Dienstag, 21. Juli 2026, 14:30 Uhr"
    )


def test_runtime_context_is_wrapped_in_a_context_block(tmp_path: Path) -> None:
    rendered = _composer(tmp_path, context=_fixed_context()).render()

    assert rendered == (
        "System\n\n<context>\n"
        "Aktueller Standort: Berlin\nAktuelle lokale Zeit: Dienstag, 21. Juli 2026, 14:30 Uhr"
        "\n</context>"
    )


def test_context_precedes_available_skills_in_the_system_prompt(tmp_path: Path) -> None:
    composer = _composer(
        tmp_path,
        skills=_skills(tmp_path, "weather", "Wetter ansagen."),
        context=_fixed_context(),
    )

    rendered = composer.render()

    assert rendered.index("<context>") < rendered.index("<available_skills>")


def test_system_prompt_is_assembled_from_the_packaged_markdown_files() -> None:
    prompt = SystemPromptComposer().render()

    assert prompt.index("<soul>") < prompt.index("<user>") < prompt.index("<memory>")


def test_system_prompt_skips_files_that_are_missing(tmp_path: Path) -> None:
    (tmp_path / "USER.md").write_text("Mathis lebt in Berlin.", encoding="utf-8")

    assert SystemPromptComposer(root=tmp_path).render() == "<user>\nMathis lebt in Berlin.\n</user>"


def test_system_prompt_can_extend_default_prompt(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("Sei direkt.", encoding="utf-8")

    prompt = SystemPromptComposer(root=tmp_path, extend_system_prompt="Nutze Tools sparsam.").render()

    assert prompt == "<soul>\nSei direkt.\n</soul>\n\nNutze Tools sparsam."


def test_system_prompt_can_override_default_prompt_while_retaining_memory(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("Sei direkt.", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("Halbmarathon im Oktober.", encoding="utf-8")

    prompt = SystemPromptComposer(root=tmp_path, override_system_prompt="Nur JSON.").render()

    assert prompt == "Nur JSON.\n\n<memory>\n<memory>\nHalbmarathon im Oktober.\n</memory>\n</memory>"


def test_system_prompt_rejects_extend_and_override_together() -> None:
    with pytest.raises(ValueError):
        SystemPromptComposer(
            override_system_prompt="Override",
            extend_system_prompt="Extend",
        )


def test_system_prompt_rejects_custom_prompt_with_override() -> None:
    with pytest.raises(ValueError):
        SystemPromptComposer(system_prompt="Custom", override_system_prompt="Override")


def test_memory_renders_files_in_order(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Halbmarathon im Oktober.", encoding="utf-8")
    (tmp_path / "DREAMS.md").write_text("Alles bleibt lokal.", encoding="utf-8")

    rendered = _composer(tmp_path).render()

    assert rendered == (
        "System\n\n<memory>\n"
        "<memory>\nHalbmarathon im Oktober.\n</memory>\n\n"
        "<dreams>\nAlles bleibt lokal.\n</dreams>\n"
        "</memory>"
    )


def test_memory_includes_only_todays_daily_note(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-01.md").write_text("Gestern.", encoding="utf-8")
    (daily / "2026-08-02.md").write_text("Heute.", encoding="utf-8")

    rendered = _composer(tmp_path, today=lambda: date(2026, 8, 2)).render()

    assert rendered == "System\n\n<memory>\n<daily>\nHeute.\n</daily>\n</memory>"


def test_memory_skips_missing_and_empty_files(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert _composer(tmp_path).render() == "System"


def test_packaged_memory_is_loaded_by_default() -> None:
    assert "<memory>" in SystemPromptComposer().render()
