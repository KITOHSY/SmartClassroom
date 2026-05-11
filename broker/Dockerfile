# syntax=docker/dockerfile:1.7

# ---- Stage 1: builder ----
FROM ghcr.io/astral-sh/uv:0.5-python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml README.md ./
COPY uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev || uv sync --no-install-project --no-dev

COPY broker ./broker
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# ---- Stage 2: runtime ----
FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/broker /app/broker
COPY --from=builder /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd -m -u 10001 broker && chown -R broker:broker /app
USER broker

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "broker.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
