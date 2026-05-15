# OpenStudy FastAPI backend
# Built by ./deploy.sh, run via docker-compose alongside postgres.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# System deps: curl for HEALTHCHECK, build tools for any source wheels.
# Slim them after the install layer to keep image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Astral) for fast dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy app source.
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations

# Final install (in case pyproject changed locally).
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Default command — overridden by compose for migrations runs.
#
# `--proxy-headers --forwarded-allow-ips '*'` makes uvicorn honor
# X-Forwarded-Proto / X-Forwarded-For from the upstream reverse proxy.
# Without this, redirects (e.g. /mcp → /mcp/) come back with `http://`
# scheme instead of `https://`, and any client following them with a
# bearer token (Claude.ai's MCP connector being the painful one) drops
# the token on the downgrade and the request fails. The wildcard is
# safe because openstudy is only reachable from the docker bridge — the
# frontend container Caddy is the only thing that sets these headers.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
