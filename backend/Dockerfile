

# ── Stage 1: dependency builder ────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install build dependencies (not needed in final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only requirements first to leverage Docker layer cache
# (re-installs only when requirements.txt changes)
COPY backend/requirements.txt /build/requirements.txt

# Install all packages into a prefix we can copy to the final stage
RUN pip install --upgrade pip setuptools wheel --quiet && \
    pip install --no-cache-dir \
        --prefix=/install \
        -r /build/requirements.txt


# ── Stage 2: production runtime ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Labels
LABEL maintainer="Curio Cloud Quiz"
LABEL description="Curio FastAPI backend"

# Install only runtime system libs (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# ── Non-root user for security ─────────────────────────────────────────────
RUN groupadd --gid 1001 appgroup && \
    useradd  --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy the entire project (backend.app.* imports need the full tree)
COPY --chown=appuser:appgroup . /app

# Create required runtime directories
RUN mkdir -p /app/static/avatars /var/log/curio && \
    chown -R appuser:appgroup /app/static /var/log/curio

# PYTHONPATH must point to /app so  backend.app.*  resolves from project root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Switch to non-root user
USER appuser

# ── Health check ────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Default command ─────────────────────────────────────────────────────────
# For production: uses Gunicorn with Uvicorn workers
# For development: override in docker-compose with uvicorn --reload
CMD ["gunicorn", "backend.app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers",      "2", \
     "--bind",         "0.0.0.0:8000", \
     "--timeout",      "120", \
     "--keep-alive",   "5", \
     "--log-level",    "info", \
     "--access-logfile", "-", \
     "--error-logfile",  "-"]
