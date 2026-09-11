# ── Stage 1: install deps ──
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-docker.txt

# ── Stage 2: runtime ──
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=deps /install /usr/local
WORKDIR /app
COPY src/ ./src/
COPY tests/ ./tests/

RUN useradd -m appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser

ENV DATA_DIR=/data \
    CONFIG_DIR=/data/config \
    AI_ENABLED=false \
    HF_HOME=/data/models \
    PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/healthz')"
CMD ["python", "-m", "uvicorn", "src.web.server:app", "--host", "0.0.0.0", "--port", "8080"]
