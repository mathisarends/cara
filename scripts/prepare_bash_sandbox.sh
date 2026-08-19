#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly PYTHON_IMAGE="python:3.14-alpine"
readonly GO_IMAGE="golang:1.25-alpine"
readonly SANDBOX_IMAGE="cara-bash-sandbox:latest"
readonly TOOLS_MANIFEST="${PROJECT_DIR}/docker/tools.txt"
readonly SKILLS_DIR="${PROJECT_DIR}/skills"

tool_names() {
    while read -r name _module _version || [[ -n "${name}" ]]; do
        case "${name}" in
            "" | '#'*) continue ;;
        esac
        echo "${name}"
    done <"${TOOLS_MANIFEST}"
}

write_skill_stub() {
    local name="$1"
    sed "s/{{cli}}/${name}/g" <<'STUB'
---
name: {{cli}}
description: >-
  Use the {{cli}} CLI. This skill is still a stub because nobody has documented
  {{cli}} yet. Load it before running the CLI; it explains how to explore the
  tool and write the real skill first.
metadata:
  status: bootstrap
  cli_binary: {{cli}}
---

# {{cli}} (not documented yet)

`{{cli}}` is installed in the sandbox, but this skill has not been written yet.

Tell the user that {{cli}} is not set up yet and that you will explore it once
before carrying out the request. Then:

1. Run `{{cli}} --help` and walk the subcommands recursively (`{{cli}} <sub> --help`).
2. Run two or three harmless read-only commands, such as status or list
   operations, to learn the output format.
3. Rewrite this `SKILL.md` so it documents the CLI's purpose, its commands,
   typical use cases, example invocations, and failure modes.
4. Follow the `cli-skill-creator` skill for format and structure.
5. Replace `status: bootstrap` with `status: ready` once the skill is complete.

Then carry out the user's original request with the commands you just documented.
STUB
}

echo "Pulling sandbox images: ${PYTHON_IMAGE}, ${GO_IMAGE}"
docker pull "${PYTHON_IMAGE}"
docker pull "${GO_IMAGE}"

echo "Building local sandbox image: ${SANDBOX_IMAGE}"
docker build \
    --pull=false \
    --tag "${SANDBOX_IMAGE}" \
    --file "${PROJECT_DIR}/docker/bash-sandbox.Dockerfile" \
    "${PROJECT_DIR}/docker"

echo "Verifying Bash, Python, and CLI tooling without pulling at runtime"
verification="bash --version | head -n 1 && python3 --version && python3 -c 'import yaml'"
for tool in $(tool_names); do
    verification+=" && ${tool} --help >/dev/null"
done

docker run \
    --rm \
    --pull=never \
    --network=none \
    "${SANDBOX_IMAGE}" \
    bash -lc "${verification}"

echo "Scaffolding skills for CLIs that are not documented yet"
for tool in $(tool_names); do
    skill_file="${SKILLS_DIR}/${tool}/SKILL.md"
    if [[ -e "${skill_file}" ]]; then
        continue
    fi
    mkdir -p "${SKILLS_DIR}/${tool}"
    write_skill_stub "${tool}" >"${skill_file}"
    echo "  created skills/${tool}/SKILL.md"
done

echo "Sandbox image is ready: ${SANDBOX_IMAGE}"
