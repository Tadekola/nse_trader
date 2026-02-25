# ── NSE Trader Backend ─────────────────────────────────────────────
# Multi-stage build: install deps in builder, copy to slim runtime.
# Data (SQLite DBs) lives in /app/data — mount as a Docker volume
# so it persists across container restarts.
# ───────────────────────────────────────────────────────────────────

# Stage 1: Install dependencies
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Production image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY ./app ./app

# Copy top-level scripts needed by background tasks
COPY fetch_real_ohlcv.py .
COPY run_backtest.py .
COPY scheduler.py .

# Copy Alembic migrations
COPY alembic.ini .
COPY alembic ./alembic

# Create data directory (will be overridden by volume mount)
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Healthcheck — hit the API health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/sources')" || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
