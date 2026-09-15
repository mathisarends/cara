from gateway.features.conversation.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from gateway.features.conversation.domain.tool_calls import ToolCallSequence

type SessionEntry = UserMessage | AssistantMessage | ToolCallSequence
