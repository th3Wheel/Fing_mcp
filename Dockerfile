# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ────────────────────────────────────────────────────────────
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --shell /bin/false appuser

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY models.py config.py server.py mcp.json ./

# ── Drop privileges ───────────────────────────────────────────────────────────
USER appuser

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["python", "server.py"]
