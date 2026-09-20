# llm

Provider-neutral message, tool, streaming-event, and `ChatModel` ports for
Cara. `PydanticAICodexModel` implements the port over Pydantic AI's Codex
provider, reads the existing Codex CLI login, and can use either HTTP or a
persistent WebSocket with automatic HTTP fallback.

HTTP remains the default. Set `CARA_LLM_TRANSPORT=websocket` (or
`llm.transport: websocket` in `gateway.yml`) to open the socket during runtime
preparation and reuse it across response turns. Automatic HTTP fallback is
limited to failures before `response.created`, where replay is still safe.
