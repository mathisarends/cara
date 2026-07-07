import pytest

from cara.messages import MessageManager, SystemPrompt


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
