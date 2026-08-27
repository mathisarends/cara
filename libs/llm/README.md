# llm

Cara's thin, application-specific configuration layer around
[`py-llmify`](https://pypi.org/project/py-llmify/)'s OpenAI Responses / Codex
provider. It doesn't define its own LLM abstraction — `llmify` already owns
the `ChatModel` protocol, message types, and streaming event model. This
package only wires Cara's model choices and Codex CLI credentials into that
provider.

```python
from llm import CodexModel, CodexReasoningEffort, create_codex_model

model = create_codex_model(CodexModel.SPARK, reasoning_effort=CodexReasoningEffort.LOW)
await model.prewarm()
```

| Name | Purpose |
| --- | --- |
| `CodexModel` | `StrEnum` of supported Codex/GPT model ids. |
| `CodexReasoningEffort` | `StrEnum` from `none` through `max`. |
| `create_codex_model()` | Returns a WebSocket-backed `llmify.ChatCodex` (via `ChatCodex.from_cli()`) — the `ChatModel` to hand to a `ModelSwitch`. |

`prewarm()` opens and retains the authenticated Responses WebSocket without
sending model input. The next stream reuses that connection.

Also re-exports `llmify`'s streaming event types
(`StreamTextDelta`, `StreamToolCall`, `StreamReasoningSummaryDelta`,
`StreamOutputItemAdded`/`Done`, `OpenAIResponsesStreamEnd`) so callers don't
need to import `llmify` directly for common handling.

## Dependencies

- `py-llmify[websocket]` — owns the actual `ChatModel` abstraction and the
  OpenAI Responses WebSocket transport.
- Consumed by [`agent`](../../agent), which passes `create_codex_model()`
  results into its `ModelSwitch`.
