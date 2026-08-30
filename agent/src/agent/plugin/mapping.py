import json

from llmify import (
    AssistantMessage,
    Function,
    Message,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from agent.events import (
    SteeringApplied,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)
from agent_plugin_api import (
    AgentAssistantMessage,
    AgentContext,
    AgentEvent,
    AgentToolCall,
    AgentToolCallSequence,
    AgentToolCallState,
    AgentUserMessage,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnSteered,
)


def context_messages(context: AgentContext) -> list[Message]:
    messages: list[Message] = []
    for entry in context.entries:
        match entry:
            case AgentUserMessage():
                messages.append(UserMessage(content=entry.content))
            case AgentAssistantMessage():
                messages.append(AssistantMessage(content=entry.content))
            case AgentToolCallSequence():
                calls = [_llm_tool_call(call) for call in entry.calls]
                messages.append(AssistantMessage(content="", tool_calls=calls))
                messages.extend(_llm_tool_result(call) for call in entry.calls)
    return messages


def _llm_tool_call(call: AgentToolCall) -> ToolCall:
    return ToolCall(
        id=call.call_id,
        function=Function(
            name=call.name,
            arguments=json.dumps(call.arguments, ensure_ascii=False),
        ),
    )


def _llm_tool_result(call: AgentToolCall) -> ToolResultMessage:
    value = call.error if call.state is AgentToolCallState.FAILED else call.result
    content = (
        "Tool completed successfully."
        if value is None
        else value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )
    return ToolResultMessage(tool_call_id=call.call_id, content=content)


def plugin_event(event: object) -> AgentEvent:
    match event:
        case TextDelta():
            return ChatDelta(event.text)
        case TurnCompleted():
            return ChatCompleted(event.text, event.finish_reason)
        case SteeringApplied():
            return TurnSteered(event.text)
        case ToolStarted():
            return ToolCallStarted(event.call_id, event.name, event.arguments)
        case ToolCompleted():
            return ToolCallCompleted(
                event.call_id,
                event.name,
                event.result,
                event.is_error,
            )
    raise TypeError(f"Unsupported Cara agent event: {type(event).__name__}")
