#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
gateway_token="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

printf '\nCARA_GATEWAY_TOKEN=%s\n' "$gateway_token" >> "$repo_root/.env"
echo "Appended a new CARA_GATEWAY_TOKEN to $repo_root/.env"
