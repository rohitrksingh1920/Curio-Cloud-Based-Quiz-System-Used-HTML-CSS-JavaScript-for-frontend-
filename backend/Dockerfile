# # ── Build stage ───────────────────────────────────────────────
# FROM python:3.11-slim AS builder

# WORKDIR /build
# COPY requirements.txt .
# RUN pip install --upgrade pip && \
#     pip install --no-cache-dir --prefix=/install -r requirements.txt

# # ── Runtime stage ─────────────────────────────────────────────
# FROM python:3.11-slim

# # libpq is needed by psycopg2-binary at runtime
# RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
#     rm -rf /var/lib/apt/lists/*

# WORKDIR /app

# # Copy installed packages from builder
# COPY --from=builder /install /usr/local

# # Copy application source
# COPY . .

# # Non-root user for security
# RUN groupadd -r appuser && useradd -r -g appuser appuser
# USER appuser

# EXPOSE 8000

# # Production: Gunicorn with Uvicorn workers
# # Development: override this in docker-compose.yml
# CMD ["gunicorn", "app.main:app", \
#      "--worker-class", "uvicorn.workers.UvicornWorker", \
#      "--workers", "2", \
#      "--bind", "0.0.0.0:8000", \
#      "--timeout", "120", \
#      "--access-logfile", "-", \
#      "--error-logfile", "-"]









# backend/Dockerfile
# Build context: project ROOT (THE2/)
# docker build -f backend/Dockerfile .

FROM python:3.11-slim

# Install system libs needed by psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy entire project (so backend.app.* imports work)
COPY . /app

# Create avatars upload directory
RUN mkdir -p /app/static/avatars

# PYTHONPATH so  backend.app.*  resolves from /app
ENV PYTHONPATH=/app

EXPOSE 8000

# Default command — override in docker-compose
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
