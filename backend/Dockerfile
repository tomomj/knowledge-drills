FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PORT=8080 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:${PATH}"

WORKDIR /app

COPY agent ./agent
COPY backend ./backend

WORKDIR /app/backend

RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
