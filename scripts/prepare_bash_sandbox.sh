#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly PYTHON_IMAGE="python:3.13-alpine"
readonly SANDBOX_IMAGE="cara-bash-sandbox:latest"

echo "Pulling sandbox base image: ${PYTHON_IMAGE}"
docker pull "${PYTHON_IMAGE}"

echo "Building local sandbox image: ${SANDBOX_IMAGE}"
docker build \
    --pull=false \
    --tag "${SANDBOX_IMAGE}" \
    --file "${PROJECT_DIR}/docker/bash-sandbox.Dockerfile" \
    "${PROJECT_DIR}/docker"

echo "Verifying Bash and Python without pulling at runtime"
docker run \
    --rm \
    --pull=never \
    --network=none \
    "${SANDBOX_IMAGE}" \
    bash -lc 'bash --version | head -n 1 && python3 --version'

echo "Sandbox image is ready: ${SANDBOX_IMAGE}"
