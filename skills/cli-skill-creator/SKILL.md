---
name: cli-skill-creator
description: Create or update a skill for a command-line tool, documenting its namespaces, exact command syntax, required parameters, and failure behavior. Use whenever the user wants to turn a CLI into a skill, document a CLI for agent use, or make an agent able to run frequent CLI tasks without repeatedly calling --help.
---

# Create a CLI Skill

The generated skill must let an agent perform frequent operations without consulting `--help`. Use help output and local docs while building it; record the resulting exact commands in the generated `SKILL.md`.

## Rules

- **Naming**: folder and frontmatter `name` = `<cli>-cli` (lowercase, hyphenated); title = `<CLI> CLI`, preserving the CLI's capitalization. Never invent a broader product or workflow name.
- **Copyable commands**: every command includes all required positional arguments. Placeholders as `<name>`, `<id>`, `<0-100>`, with their format stated.
- **Shortest correct command**: include a flag only when it is required, prevents ambiguity, improves safety, or produces output the workflow consumes. Never add `--json`, `--no-color`, verbosity, or field filters by default.
- **No intent maps**: assume the agent maps "pause" or "set volume to 35" to a clearly named operation. Use examples only for non-obvious syntax, mandatory flag combinations, or surprising behavior.
- **Layering**: frequent operations stay in `SKILL.md`. Rare or large namespaces go to `references/<namespace>.md`, linked from `SKILL.md`.
- **Portability**: the skill stays reusable across setups. It documents syntax and placeholders only. Concrete values that shortcut discovery in one specific setup — resource IDs, device or room names, account handles, default targets — belong in the workspace's `tools.md`, never in the skill. Where such a value is expected, name the placeholder and point at `tools.md`.
- **Safety**: never run destructive or externally consequential commands without explicit authorization.

## Explore

Run `--help` at top level and per namespace. Record:

| Finding                                                       | Feeds into        |
| ------------------------------------------------------------- | ----------------- |
| version, global options, auth/preconditions                   | intro line        |
| namespaces and their purpose                                  | Namespaces table  |
| commands that list real resource names                        | Discovery         |
| command shape and argument order                              | Common operations |
| required vs. behavior-changing vs. optional flags             | flag filtering    |
| resource types needing extra arguments, quoting, value ranges | Exceptions        |
| read command confirming each mutation                         | Verification      |
| output modes, exit codes, clamping, rate limits, errors       | Failure behavior  |

## Output template

Write `SKILL.md` in exactly this order. Omit a section only if it genuinely does not apply.

````markdown
---
name: <cli>-cli
description: <what the CLI controls>. Use whenever <concrete task categories>.
---

# <CLI> CLI

<one line: what it controls, plus auth or preconditions>

## Namespaces

| Group | Controls | Notes |
| ----- | -------- | ----- |

## Discovery

Known IDs and names for this workspace are in `tools.md`. Use them if present; otherwise discover:

```bash
<commands revealing real resource names, run before acting>
```

## Common operations

```bash
<exact read and write commands, grouped by namespace>
```

## Exceptions

<mandatory parameter combinations, resource-specific extra arguments, quoting, value ranges>

## Verification

```bash
<read command confirming each mutation>
```

## Failure behavior

<exit codes, clamping, rate limits, common errors>
````

## Validate

1. Walk one path per category: discovery → read → mutation → error handling. Mutations only in a safe test environment or with explicit authorization.
2. Compare observed syntax, output, and errors against what the skill claims. Fix mismatches; delete flags and examples that proved unnecessary.
3. Repeat until every frequent operation is executable from `SKILL.md` alone.
4. From the repository root, run
   `python skills/cli-skill-creator/scripts/quick_validate.py skills/<cli>-cli`.
   Use workspace-relative paths for file tools (`.` is the workspace root, never
   `/`) and locate files with the workspace glob tool instead of recursively
   scanning unrelated or inaccessible directories with shell `find`.
5. If validation or runtime skill discovery reports an in-scope skill error, diagnose and fix it immediately, then rerun the failing check. Do not stop after merely reporting a fixable error.
6. In the final response, explicitly identify every error that this skill fixed automatically and report the final validation result.
