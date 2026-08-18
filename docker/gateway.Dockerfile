FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies resolve from the workspace manifests alone, so they stay cached
# until a pyproject or the lock file changes.
COPY pyproject.toml uv.lock ./
COPY agent/pyproject.toml agent/
COPY gateway/pyproject.toml gateway/
COPY gateway_client/pyproject.toml gateway_client/
COPY llm/pyproject.toml llm/
COPY scheduler/pyproject.toml scheduler/
COPY voice/pyproject.toml voice/
RUN uv sync --frozen --package gateway --no-install-workspace

COPY . .
RUN uv sync --frozen --package gateway

EXPOSE 8000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
