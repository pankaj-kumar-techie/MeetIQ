# ── Stage 1: dependencies ─────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

# Install build tools for packages that need compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# libpq runtime only (for asyncpg) + curl for healthchecks + ffmpeg for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy application source
COPY . .

# Create data directory for SQLite
RUN mkdir -p /data

EXPOSE 8000

# Use uvicorn with 2 workers (1 for local dev is fine too)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
