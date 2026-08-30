# cli

Small interactive terminal client for manually exercising the Cara Gateway
during development. Connects over JSON-RPC/WebSocket via
[`gateway_client`](../gateway/client), opens or resumes a session on a given
channel, and renders the streamed reply — including tool-call events — live.

Typing stays live while a turn runs: a message sent during a turn is queued
with `turn.steer` and reaches the model at its next tool-call boundary, and
`esc` interrupts the turn so anything still queued is resent as a new turn.
Both need a terminal; with stdin redirected the client falls back to reading
whole lines, where `esc` is unavailable and `/cancel` interrupts instead.

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
├── main.py       argument parsing, connection, top-level error handling
├── chat.py       ChatSession: session lifecycle, commands, steering, rendering
├── keyboard.py   raw-mode key events from stdin, with a line-mode fallback
└── console.py    stdout: colored output above a live prompt line
```
