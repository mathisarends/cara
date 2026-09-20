#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Removes Python cache directories, compiled files and the source folders they
# leave empty behind. Pass --check to list what would go without deleting it.

check=0
if [[ "${1:-}" == "--check" ]]; then
  check=1
  shift
fi
if [[ $# -gt 0 ]]; then
  echo "usage: $(basename "$0") [--check]" >&2
  exit 2
fi

skip=(-name .git -o -name .venv -o -name node_modules -o -name temp)
caches=(-name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache -o -name '*.egg-info')

find_caches() {
  find . \( "${skip[@]}" \) -prune -o \( "${caches[@]}" \) -type d -prune "$@"
}

find_compiled() {
  find . \( "${skip[@]}" -o "${caches[@]}" \) -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) "$@"
}

find_empty_dirs() {
  find . -mindepth 1 \( "${skip[@]}" -o "${caches[@]}" \) -prune -o -type d -empty "$@"
}

# Directories whose only content is a cache tree become empty once it is gone.
find_soon_empty_dirs() {
  find . -mindepth 1 \( "${skip[@]}" \) -prune -o \( "${caches[@]}" \) -prune -o -type d -print |
    while read -r dir; do
      if [[ -z "$(find "$dir" -mindepth 1 \( "${caches[@]}" \) -prune -o -print -quit)" ]]; then
        echo "$dir"
      fi
    done
}

if [[ $check -eq 1 ]]; then
  echo "== cache directories =="
  find_caches -print
  echo "== compiled files outside them =="
  find_compiled -print
  echo "== directories left empty afterwards =="
  find_soon_empty_dirs
  exit 0
fi

# A single locked entry must not abort the rest of the cleanup.
status=0
find_caches -exec rm -rf {} + || status=1
find_compiled -exec rm -f {} + || status=1

# Repeat until stable so parents of removed directories collapse too.
while [[ -n "$(find_empty_dirs -print -quit)" ]]; do
  find_empty_dirs -exec rmdir {} + || { status=1; break; }
done

if [[ $status -ne 0 ]]; then
  echo "$(basename "$0"): some entries could not be removed (see errors above)" >&2
fi
exit $status
