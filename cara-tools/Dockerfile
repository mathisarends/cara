FROM python:3.13-slim

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY . .
RUN uv sync --frozen --package cara-tools --no-dev

CMD [".venv/bin/python", "-m", "cara_tools.main"]
