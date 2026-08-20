# Agent Protocol

`agent-protocol` is the canonical Python contract for Cara's conversation
WebSocket. It contains the Pydantic wire models, JSON-RPC request and response
unions, event types, adapters, and a typed async client. It does not depend on
the gateway, persistence, FastAPI, or the agent runtime.

The gateway exposes the same contract as JSON Schema at
`GET /v1/conversation/schema`. Python consumers should depend on this package
directly; other consumers can generate types from that schema.
