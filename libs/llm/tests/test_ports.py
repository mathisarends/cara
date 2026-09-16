from pydantic import TypeAdapter

from llm import Message, MessageType, ModelEvent, ModelEventType, TextDelta, UserMessage


def test_message_discriminator_deserializes_to_the_concrete_message() -> None:
    adapter = TypeAdapter(Message)

    message = adapter.validate_python({"type": "user", "content": "Hello"})

    assert message == UserMessage(content="Hello")
    assert message.type is MessageType.USER


def test_model_event_discriminator_deserializes_to_the_concrete_event() -> None:
    adapter = TypeAdapter(ModelEvent)

    event = adapter.validate_python({"type": "text_delta", "delta": "Hello"})

    assert event == TextDelta(delta="Hello")
    assert event.type is ModelEventType.TEXT_DELTA
