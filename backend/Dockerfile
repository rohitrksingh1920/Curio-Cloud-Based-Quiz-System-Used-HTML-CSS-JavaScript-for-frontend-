# ── Build stage ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────
FROM python:3.11-slim

# libpq is needed by psycopg2-binary at runtime
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

EXPOSE 8000

# Production: Gunicorn with Uvicorn workers
# Development: override this in docker-compose.yml
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
