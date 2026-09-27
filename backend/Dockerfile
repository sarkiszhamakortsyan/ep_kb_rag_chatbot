# Backend image: installs the locked dependencies with uv in a builder stage, then runs the FastAPI
# app with uvicorn on port 8000 as a non-root user.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# --- dependencies (cached unless pyproject/uv.lock change) ---
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- runtime ---
FROM base AS runtime
RUN useradd --create-home --uid 1000 appuser
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY app ./app
COPY data/kb ./data/kb
# The benchmark question set, for the admin Tests tab (same path as in the repo)
COPY tests/eval/questions.yaml ./tests/eval/questions.yaml
RUN mkdir -p data/index data/db data/models && chown -R appuser:appuser data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:api", "--host", "0.0.0.0", "--port", "8000"]
