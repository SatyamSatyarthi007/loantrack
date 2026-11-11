# Multi-stage Dockerfile for LoanTrack Backend
# Pinned to python:3.12-slim for reproducible builds and glibc wheel compatibility

# Stage 1: Build dependency virtual environment
FROM python:3.12-slim AS builder

WORKDIR /build

# Cache boundary: copy dependencies manifest first so changes to application code
# do not invalidate the pip installation layer cache
COPY requirements.txt .

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Minimal runtime image (< 300 MB target)
FROM python:3.12-slim

# Create dedicated non-root system user with explicit numeric UID (required for K8s runAsNonRoot)
RUN useradd --system --uid 10001 --no-create-home appuser

WORKDIR /app

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source code
COPY app.py .

# Build argument allowing version customization during build (e.g. Phase 4 rolling update)
ARG APP_VERSION=v1
ENV APP_VERSION=$APP_VERSION \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Run as non-root numeric user 10001
USER 10001

EXPOSE 8000

# Container healthcheck testing /healthz (liveness, DB-independent) using Python stdlib (no curl needed)
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=2)" || exit 1

# Production WSGI server with 2 worker processes
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "app:app"]
