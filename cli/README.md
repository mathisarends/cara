# cli

Small interactive terminal client for manually exercising the Cara Gateway
during development. Connects over JSON-RPC/WebSocket via
[`gateway_client`](../gateway/client), opens or resumes a session on a given
channel, and renders the streamed reply — including tool-call events — live.

## Running

```bash
uv run cara-chat
```

Requires `CARA_GATEWAY_TOKEN` (same shared token as the Gateway). Flags:
`--url`, `--channel`, `--account`, `--session`, `--events`, `--no-color` — no
env vars or config files otherwise.

In-session commands: `/new`, `/session`, `/history`, `/events`, `/cancel`,
`/quit`.

## Dependencies

- [`gateway_client`](../gateway/client) — typed RPC client and event models.
- A running [`gateway-server`](../gateway/server) to connect to.

## Layout

```text
cli/src/cli/
├── main.py      argument parsing, connection, top-level error handling
├── chat.py       ChatSession: session lifecycle, REPL commands, rendering
└── console.py    ANSI-colored terminal output helpers
```
