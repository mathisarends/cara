#!/bin/sh
set -eu

manifest="$1"

while read -r name module version || [ -n "$name" ]; do
  case "$name" in
    ""|\#*) continue ;;
  esac
  if [ -z "$module" ] || [ -z "$version" ]; then
    echo "Manifest entry '$name' needs a module and a version." >&2
    exit 1
  fi
  echo "Installing ${name}@${version} (${module})"
  go install -trimpath -ldflags="-s -w" "${module}@${version}"
  if [ ! -x "${GOBIN}/${name}" ]; then
    echo "Module '${module}' did not install a binary named '${name}'." >&2
    exit 1
  fi
done < "$manifest"
