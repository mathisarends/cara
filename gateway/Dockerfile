FROM python:3.13-slim

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY . .
RUN uv sync --frozen --package gateway-server --no-dev

ENV CARA_GATEWAY_HOST=0.0.0.0
CMD [".venv/bin/python", "-m", "gateway.main"]
