---
name: spoti
description: >-
  Use the spoti CLI. This skill is still a stub because nobody has documented
  spoti yet. Load it before running the CLI; it explains how to explore the
  tool and write the real skill first.
metadata:
  status: bootstrap
  cli_binary: spoti
---

# spoti (not documented yet)

`spoti` is installed in the sandbox, but this skill has not been written yet.

Tell the user that spoti is not set up yet and that you will explore it once
before carrying out the request. Then:

1. Run `spoti --help` and walk the subcommands recursively (`spoti <sub> --help`).
2. Run two or three harmless read-only commands, such as status or list
   operations, to learn the output format.
3. Rewrite this `SKILL.md` so it documents the CLI's purpose, its commands,
   typical use cases, example invocations, and failure modes.
4. Follow the `cli-skill-creator` skill for format and structure.
5. Replace `status: bootstrap` with `status: ready` once the skill is complete.

Then carry out the user's original request with the commands you just documented.
