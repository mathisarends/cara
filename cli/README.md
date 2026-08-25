# cli

`cli` is a small interactive terminal client for manually exercising the Cara
Gateway during development. It connects over JSON-RPC/WebSocket via
[`gateway_client`](../gateway/client), resolves or reuses a session on a given
channel, and gives you a REPL where you type messages and watch the
assistant's streamed reply — including tool-call events — render live.

## Table of contents

- [Running it](#running-it)
- [Flow](#flow)
- [Commands](#commands)
- [Module layout](#module-layout)

## Running it

Set `CARA_GATEWAY_TOKEN` to the same shared token as the Gateway. The CLI sends
it as a Bearer credential during the WebSocket handshake.

```bash
uv run cara-chat
```

```text
usage: cara-chat [--url URL] [--channel CHANNEL] [--account ACCOUNT]
                  [--session SESSION_ID] [--events] [--no-color]
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--url` | `ws://127.0.0.1:8000/v1/gateway` | Gateway WebSocket endpoint. |
| `--channel` | `cli` | Channel whose *current* session is opened. |
| `--account` | — | Optional account id scoping the channel. |
| `--session` | — | Attach to a specific session UUID instead of the channel's current one. |
| `--events` | off | Print the raw event trace instead of rendered chat. |
| `--no-color` | off | Disable ANSI colors. |

There are no environment variables or config files to set — everything a run
needs comes from these flags plus an already-running Gateway.

## Flow

1. **Connect.** `GatewayClient.connect(url)` opens the WebSocket; a failure to
   reach the Gateway exits immediately with an error.
2. **Resolve the session.** With no `--session`, `cli` calls
   `client.session.open(channel=...)` — the same channel-scoped reuse
   `session.open` provides to any client (see [`gateway-server`](../gateway/server)): it
   returns the channel's existing session or creates one, so re-running
   `cara-chat` against the same `--channel`/`--account` continues the same
   conversation. This is entirely server-side — the CLI stores no session id
   on disk between runs, only in memory for the current process. `/new`
   bypasses reuse and always starts a fresh session on the channel.
3. **Attach.** The client fetches a snapshot via `client.session.get(...)`,
   replays it into the terminal, then `client.subscription.subscribe(...)` to
   start receiving live events.
4. **Send.** Each non-command line becomes `client.turn.start(session_id=...,
   message=...)`; the prompt blocks until a `TurnCompleted` / `TurnCancelled`
   / `TurnFailed` notification arrives (or the connection drops).
5. **Render.** A background task drains `client.notifications()` and renders
   each `SessionEvent`: `ChatDelta` streams token-by-token with no newline,
   `ToolCallStarted`/`ToolCallCompleted` print as `→ name(args)` /
   `✓ name: result` (or `✗` on error, truncated to 80 characters), and
   `TurnCompleted`/`TurnFailed`/`TurnCancelled` end the current line.
6. **Exit.** `/quit`, `/exit`, `/q`, or Ctrl+C leave cleanly; a dropped Gateway
   connection also unblocks the prompt loop with a warning.

## Commands

```text
/new              start a fresh session on the channel
/session          show the current session id
/history          replay the session snapshot from the gateway
/events           toggle the raw event trace
/cancel           cancel the running turn
/quit             leave (ctrl-c works too)
```

## Module layout

```text
cli/src/cli/
├── __init__.py    re-exports main
├── main.py          argument parsing, Gateway connection, top-level error handling
├── chat.py           ChatSession: session lifecycle, REPL commands, event rendering
└── console.py        Console: ANSI-colored terminal output helpers
```
