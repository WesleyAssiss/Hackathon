# syntax=docker/dockerfile:1.7

# ── Builder ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY frontend ./frontend
COPY data ./data

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install ".[azure]"

# ── Runtime ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AURA_USE_MANAGED_IDENTITY=true

# Non-root for security baseline.
RUN useradd --create-home --uid 10001 aura
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/backend /app/backend
COPY --from=builder /build/frontend /app/frontend
COPY --from=builder /build/data /app/data

ENV PYTHONPATH=/app/backend
USER aura
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else sys.exit(1)"

CMD ["uvicorn", "aura.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
