# syntax=docker/dockerfile:1
# ── base: runtime deps + app code ────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY config.py fing_client.py models.py server.py mcp.json ./

# ── test: dev deps installed as root at build time, then run pytest ──────────
FROM base AS test
COPY requirements-dev.txt pyproject.toml ./
RUN pip install -r requirements-dev.txt
COPY scripts ./scripts
COPY tests ./tests
CMD ["sh", "-c", "ruff check . && python scripts/gen_manifest.py --check && pytest -v --tb=short"]

# ── runtime: non-root, streamable HTTP on :8000 ──────────────────────────────
FROM base AS runtime
RUN groupadd --system app && useradd --system --gid app --no-create-home --shell /usr/sbin/nologin app
USER app

ENV MCP_TRANSPORT=http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request,sys; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MCP_PORT\",\"8000\")}/healthz', timeout=4); sys.exit(0)" || exit 1

CMD ["python", "server.py"]
