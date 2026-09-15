FROM python:3.13-slim

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY . .
RUN uv sync --frozen --package sandbox-manager --no-dev

CMD [".venv/bin/python", "-m", "sandbox_manager.main"]
