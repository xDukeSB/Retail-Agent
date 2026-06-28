FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependency layer (cached unless requirements.txt changes) ──────────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Development image ──────────────────────────────────────────────────────────
FROM deps AS development
COPY . .
ENV PYTHONPATH=/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production image ───────────────────────────────────────────────────────────
FROM deps AS production
COPY . .

# Non-root user
RUN groupadd --gid 1001 retailai \
 && useradd  --uid 1001 --gid retailai --no-create-home retailai

# Data directories (volume-mounted in prod)
RUN mkdir -p /data/db /data/reports /data/models \
 && chown -R retailai:retailai /data /app

USER retailai
ENV PYTHONPATH=/app \
    ENVIRONMENT=production \
    LOG_FORMAT=json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ready || exit 1

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--access-log"]
