# Cara

Cara is starting fresh. [vision.md](vision.md) describes the product ambition and technical qualities that guide the new implementation. The technology stack and architecture remain open.

## Repository contents

- [vision.md](vision.md): the product and technical vision, including room-aware interaction, integrations, persistent tasks, and subagent coordination.
- [libs/voice](libs/voice): the previous voice package, preserved unchanged with its source, tests, and assets as a reference.
- [AGENTS.md](AGENTS.md): repository instructions for coding agents.

The retained voice package depends on components from the archived implementation, including generated Gateway clients and the former workspace configuration. It is a reference for the rewrite and is not a standalone runnable application in this repository state.

## Archived implementation

The complete implementation before the rewrite is preserved under:

- Branch: `codex/archive/pre-rewrite-2026-10-30`
- Annotated tag: `archive/pre-rewrite-2026-10-30`

The archive includes the local room integration specification changes. Its snapshot's second parent also preserves the original staged state.
