# llm

Provider-neutral message, tool, streaming-event, and `ChatModel` ports for
Cara. `PydanticAICodexModel` implements the port over Pydantic AI's Codex
provider, reads the existing Codex CLI login, and can use either HTTP or a
persistent WebSocket with automatic HTTP fallback.

WebSocket is the default and opens during runtime preparation so it can be
reused across response turns. Preparation also sends `response.create` with
`generate=false`, allowing the next user message to continue from the warmed
request state. Set `CARA_LLM_TRANSPORT=http` (or `llm.transport: http` in
`gateway.yml`) to force HTTP. Automatic HTTP fallback is limited to failures
before `response.created`, where replay is still safe.
