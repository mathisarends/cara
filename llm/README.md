# llm

`llm` is Cara's thin, application-specific configuration layer around
[`py-llmify`](https://pypi.org/project/py-llmify/)'s OpenAI Responses / Codex
provider. It does not define its own LLM abstraction — `llmify` already owns
the `ChatModel` protocol, message types, and streaming event model. This
package only wires Cara's model choices and Codex CLI credentials into that
provider.

## Table of contents

- [Installation](#installation)
- [Public API](#public-api)
- [Creating a model](#creating-a-model)
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

## Creating a model

`create_codex_model()` is the integration point [`agent`](../agent) uses: it
resolves Codex CLI credentials via `ChatCodex.from_cli()` rather than a plain
API key, and forwards only Cara's explicitly supported configuration to
`llmify`:

```python
from llm import CodexModel, CodexReasoningEffort, create_codex_model

model = create_codex_model(
    CodexModel.SPARK,
    reasoning_effort=CodexReasoningEffort.LOW,
)
```

Only `model` and the optional `reasoning_effort` are exposed. When no reasoning
effort is supplied, the factory omits that argument entirely and leaves the
provider default untouched.

## Streaming events

The `ChatModel` returned by `create_codex_model()` yields `llmify`'s
`OpenAIResponsesStreamEvent` union, re-exported here so callers don't need to
import `llmify` directly for common handling:

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
└── codex.py        CodexModel, CodexReasoningEffort, create_codex_model
```
