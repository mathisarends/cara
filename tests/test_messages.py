import pytest
from llmify import AssistantMessage, Function, ToolCall, ToolResultMessage

from cara.messages import MessageManager, SystemPrompt
from cara.skills import Skill, SkillRepository


def _tool_call() -> ToolCall:
    return ToolCall(id="call-1", function=Function(name="load_skill", arguments="{}"))


def test_message_manager_builds_llm_messages_with_system_prompt() -> None:
    messages = MessageManager(system_prompt="System", max_turns=1)

    messages.add_user("Hi")
    messages.add_assistant("Hallo")

    llm_messages = messages.to_llm_messages()

    assert llm_messages[0].content == "System"
    assert llm_messages[1].content == "Hi"
    assert llm_messages[2].content == "Hallo"


def test_message_manager_trims_to_max_turns() -> None:
    messages = MessageManager(system_prompt="System", max_turns=1)

    messages.add_user("one")
    messages.add_assistant("two")
    messages.add_user("three")

    llm_messages = messages.to_llm_messages()

    assert [message.content for message in llm_messages] == ["System", "two", "three"]


def test_tool_result_lands_in_context_paired_with_its_call() -> None:
    messages = MessageManager(system_prompt="System")

    messages.add_user("Read this PDF")
    messages.add_tool_result(_tool_call(), "Use the bundled parser.")
    messages.add_assistant("Mache ich.")

    llm_messages = messages.to_llm_messages()

    assistant_call, tool_result = llm_messages[2], llm_messages[3]
    assert isinstance(assistant_call, AssistantMessage)
    assert assistant_call.tool_calls[0].id == "call-1"
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.content == "Use the bundled parser."


def test_available_skills_are_appended_to_the_system_prompt() -> None:
    skills = SkillRepository([Skill(name="pdf", description="Read PDFs.", instructions="...")])
    messages = MessageManager(system_prompt="System", skills=skills)

    rendered = messages.to_llm_messages()[0].content

    assert rendered == "System\n\n<available_skills>\n- pdf: Read PDFs.\n</available_skills>"


def test_empty_skill_repository_leaves_the_system_prompt_untouched() -> None:
    messages = MessageManager(system_prompt="System", skills=SkillRepository())

    assert messages.to_llm_messages()[0].content == "System"


def test_trim_drops_tool_results_orphaned_from_their_call() -> None:
    messages = MessageManager(system_prompt="System", max_turns=1)

    messages.add_tool_result(_tool_call(), "instructions")
    messages.add_user("three")

    assert not any(isinstance(message, ToolResultMessage) for message in messages.to_llm_messages())


def test_system_prompt_reads_default_markdown() -> None:
    prompt = SystemPrompt().render()

    assert "Du bist Cara" in prompt


def test_system_prompt_can_extend_default_prompt() -> None:
    prompt = SystemPrompt(extend_system_prompt="Nutze Tools sparsam.").render()

    assert "Du bist Cara" in prompt
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
