# AGENTS.md - Your Workspace

This folder is home. Treat it that way.

## Session Startup

Use runtime-provided startup context first.

It may already include:

- AGENTS.md
- SOUL.md
- USER.md
- recent daily memory
- MEMORY.md

Do not manually reread startup files unless needed.

## Progress Updates

For tasks that require multiple tool calls or take noticeable time, keep the user
informed with short, natural-language progress updates. Send an initial update
before starting tool work, then another update whenever a meaningful result is
found or the next phase begins. Continue using tools after an update when more
work remains, and finish with a self-contained final answer.

Do not register or call a dedicated progress-update tool. Progress updates are
ordinary assistant text. Keep them concise and useful; skip them for simple,
immediate tasks and avoid narrating every minor tool call.
