# llm

`llm` is Cara's thin, application-specific configuration layer around
[`py-llmify`](https://pypi.org/project/py-llmify/)'s OpenAI Responses / Codex
provider. It does not define its own LLM abstraction — `llmify` already owns
the `ChatModel` protocol, message types, and streaming event model. This
package only wires Cara's model choices and Codex CLI credentials into that
provider, and adds a small stateful session helper for turn-by-turn chat.

## Table of contents

- [Installation](#installation)
- [Public API](#public-api)
- [Creating a model](#creating-a-model)
- [Stateful sessions](#stateful-sessions)
- [Streaming events](#streaming-events)
- [Module layout](#module-layout)

## Installation

Requires Python 3.13. Part of the `cara` uv workspace; add it as a workspace
dependency like any other package here.

## Public API

```python
from llm import (
    CodexModel,
    CodexReasoningEffort,
    CodexSession,
    create_codex_model,
    # re-exported from llmify, for handling stream events:
    OpenAIResponsesStreamEnd,
    OpenAIResponsesStreamEvent,
    StreamOutputItemAdded,
    StreamOutputItemDone,
    StreamReasoningSummaryDelta,
    StreamTextDelta,
    StreamToolCall,
)
```

| Name | Purpose |
| --- | --- |
| `CodexModel` | `StrEnum` of the Codex/GPT model ids Cara supports (`gpt-5.3-codex-spark`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`, `gpt-5.5`, `gpt-5.4`). |
| `CodexReasoningEffort` | `StrEnum` from `none` through `max`, mapped onto `llmify`'s `ReasoningEffort`. |
| `create_codex_model()` | Factory returning a configured `llmify.ChatCodex` — the `ChatModel` implementation to hand to a `ModelSwitch` (see [`agent`](../agent)). |
| `CodexSession` | A small, self-contained chat session with in-memory history — for standalone use outside the full [`agent`](../agent) loop. |

## Creating a model

`create_codex_model()` is the integration point [`agent`](../agent) uses: it
resolves Codex CLI credentials via `ChatCodex.from_cli()` rather than a plain
API key, and forwards Cara's enums plus any Responses-API option straight
through to `llmify`:

```python
from llm import CodexModel, CodexReasoningEffort, create_codex_model

model = create_codex_model(
    CodexModel.SPARK,
    reasoning_effort=CodexReasoningEffort.LOW,
)
```

Everything past `model` and `reasoning_effort` — `max_tokens`, `temperature`,
`top_p`, `store`, `continuation_mode`, `prompt_cache_key`,
`prompt_cache_options`, `timeout`, `max_retries`, `default_headers`, and any
other `ChatCodex.from_cli()` keyword — is accepted and passed through
unchanged, so this package never has to catch up with new Responses API
options.

## Stateful sessions

`CodexSession` is a lightweight alternative for scripts and standalone tools
that don't need the full [`agent`](../agent) loop (tool calling, sandboxing,
prompt assembly) — just a model that remembers what was said:

```python
from llm import CodexSession, CodexReasoningEffort, StreamTextDelta

session = CodexSession(
    instructions="Be concise.",
    reasoning_effort=CodexReasoningEffort.LOW,
)

async for event in session.stream("Hi"):
    if isinstance(event, StreamTextDelta):
        print(event.delta, end="")
```

Each `stream(text)` call appends a `UserMessage`, streams the reply, and —
once the stream ends — appends an `AssistantMessage` (with any tool calls
observed along the way) to the session's history, so the next `stream()` call
continues the same conversation. `agent.Agent` does not use `CodexSession`
directly; it calls `create_codex_model()` and drives the resulting
`ChatModel` itself, since it needs full control over tool execution between
completions.

## Streaming events

Both `create_codex_model()`'s `ChatModel.stream()` and `CodexSession.stream()`
yield `llmify`'s `OpenAIResponsesStreamEvent` union, re-exported here so
callers don't need to import `llmify` directly for common handling:

| Event | Carries |
| --- | --- |
| `StreamTextDelta` | `delta: str` — one chunk of assistant text. |
| `StreamToolCall` | `tool_call: ToolCall` — a completed tool call (`.id`, `.function.name`, `.function.arguments`). |
| `StreamReasoningSummaryDelta` | `delta: str` — one chunk of reasoning/thinking summary text. |
| `StreamOutputItemAdded` / `StreamOutputItemDone` | Lifecycle events for a Responses API output item. |
| `OpenAIResponsesStreamEnd` | Terminal event for the stream. |

## Module layout

```text
llm/src/llm/
├── __init__.py    public exports
└── codex.py        CodexModel, CodexReasoningEffort, create_codex_model, CodexSession
```
