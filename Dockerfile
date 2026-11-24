# PC-AMD7900X already caches this CUDA base image. Keep builds offline from
# Docker Hub with Compose `pull: false`; Python packages may still use PyPI.
FROM nvidia/cuda:12.4.1-base-ubuntu22.04 AS deps
WORKDIR /app
COPY requirements-docker.txt .
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir nvidia-cublas-cu12 nvidia-cudnn-cu12 \
 && /opt/venv/bin/pip install --no-cache-dir --requirement requirements-docker.txt \
 && rm -rf /var/lib/apt/lists/*

# ── Stage 2: cached CUDA runtime ──
FROM nvidia/cuda:12.4.1-base-ubuntu22.04
ARG TARGETARCH=amd64
ARG TYPST_VERSION=0.13.1
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 ffmpeg ca-certificates curl tar xz-utils fonts-dejavu \
 && case "$TARGETARCH" in \
      amd64) typst_arch="x86_64-unknown-linux-musl" ;; \
      arm64) typst_arch="aarch64-unknown-linux-musl" ;; \
      *) echo "Unsupported TARGETARCH=$TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${typst_arch}.tar.xz" -o /tmp/typst.tar.xz \
 && tar -xJf /tmp/typst.tar.xz -C /tmp \
 && install -m 0755 "/tmp/typst-${typst_arch}/typst" /usr/local/bin/typst \
 && typst --version \
 && rm -rf /tmp/typst* /var/lib/apt/lists/*
COPY --from=deps /opt/venv /opt/venv
# cuDNN wheels install shared libraries under the venv rather than /usr/lib.
ENV PATH=/opt/venv/bin:$PATH \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.10/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.10/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}
WORKDIR /app
COPY src/ ./src/
COPY tests/ ./tests/

RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /data \
 && chown --recursive appuser:appuser /data

ENV DATA_DIR=/data \
    CONFIG_DIR=/data/config \
    AI_ENABLED=false \
    HF_HOME=/data/models \
    PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz', timeout=3)"
CMD ["python", "-m", "uvicorn", "src.web.server:app", "--host", "0.0.0.0", "--port", "8080"]
