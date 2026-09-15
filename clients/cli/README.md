# cli

Small interactive terminal client for manually exercising the Cara Gateway
during development. Opens or resumes a session on a given channel over REST via
[`gateway_rest_client`](../../generated/gateway_rest_client), runs turns over the
JSON-RPC WebSocket via [`gateway_rpc_client`](../../generated/gateway_rpc_client),
and renders the streamed reply — including tool-call events — live.

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
`--url` (Gateway base URL, default `http://127.0.0.1:8000`), `--channel`,
`--session`, `--events`, `--no-color` — no env vars or config files otherwise.

In-session commands: `/new`, `/session`, `/history`, `/events`, `/cancel`,
`/help`, `/quit`.

## Commands and completion

`commands.py` is the single list behind `/help`, the completion menu and the
dispatcher, so a command cannot show up in one and be missing from another.

The prompt line holds nothing but what you typed. The hint (`type a message · /
for commands · tab completes`, or `type to steer · esc to interrupt` while a
turn runs) sits on its own dim row above it and disappears at the first
keystroke, so it can never read as text already written for you.

Typing `/` opens a menu of the matching commands just above the prompt, inside
the same live region, so it disappears again the moment the line is sent. `tab`
writes the first match into the line and further tabs walk the matches that were
frozen at the first press — editing the line starts a fresh cycle. Completion
needs a terminal; with stdin redirected a tab is just a character.

## Tool calls

A call is rendered as a headline and, once it returns, an indented result:

```text
  ● read_note  Daily/2026-08-30.md
    ↳ # 30. August
      - Review
      - Deploy
      +2 more lines
  ● write_note  Inbox/idee.md · content='…'
    ✗ ValueError: refusing to overwrite an existing note
```

The first argument carries the call — a path, a query, a command — so it is
shown bare and the rest stay named behind it. Results are cut to a few lines
with the remainder counted, and a failed call is marked `✗` in red instead of
`↳`. A replayed snapshot renders the same way; a call still pending shows its
headline and no result.

## Dependencies

- [`gateway_rest_client`](../../generated/gateway_rest_client) — sessions and snapshots.
- [`gateway_rpc_client`](../../generated/gateway_rpc_client) — turns, subscriptions, and event models.
- A running [`gateway-server`](../../gateway) to connect to.

## Layout

```text
clients/cli/src/cli/
├── main.py       argument parsing, connection, top-level error handling
├── chat.py       ChatSession: session lifecycle, commands, steering, rendering
├── commands.py   the slash commands: help text, completion, dispatch
├── keyboard.py   raw-mode key events from stdin, with a line-mode fallback
└── console.py    stdout: colored output above a live prompt and its completions
```
