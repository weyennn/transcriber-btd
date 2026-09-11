### Task 6: Artefak Docker — requirements, Dockerfile, compose, .dockerignore

**Files:**
- Create: `requirements-docker.txt`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`

**Interfaces:**
- Consumes: semua env var dari Task 1-4 (`DATA_DIR`, `CONFIG_DIR`, `AI_ENABLED`, `HF_HOME`, `PORT`)
- Produces: image `mesin-transcribe` dan service compose yang dipakai Task 7 (verifikasi).

- [ ] **Step 1: `requirements-docker.txt`**

```
fastapi>=0.110
uvicorn>=0.29
python-multipart>=0.0.9
faster-whisper>=1.2.0
ctranslate2>=4.8.1
huggingface_hub>=1.26.0
python-docx>=1.0.0
httpx>=0.27
pytest>=8.0
```

- [ ] **Step 2: `Dockerfile`** — persis dari spec §5.1, plus `CONFIG_DIR` di ENV dan healthcheck ke `/healthz`:

```dockerfile
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
```

- [ ] **Step 3: `docker-compose.yml`** — persis dari spec §5.2:

```yaml
services:
  transcribe:
    build: .
    container_name: mesin-transcribe
    restart: unless-stopped
    ports:
      - "8765:8080"
    volumes:
      - ./data/models:/data/models
      - ./data/uploads:/data/uploads
      - ./data/hasil:/data/hasil
      - ./data/config:/data/config
    environment:
      AI_ENABLED: "false"
      # TRANSCRIBE_AI_BASE_URL: http://<host-9router>:20128/v1   # aktifkan bersama AI_ENABLED=true
    mem_limit: 4g
```

- [ ] **Step 4: `.dockerignore`** — persis dari spec §5.3:

```
.venv/
.venv-mac/
.pytest_cache/
__pycache__/
*.pyc
.DS_Store
data/
uploads/*
transcribe_hasil/
sample_audio/
tests/baseline_output/
main.py
src/gui/
src/services/
docs/
```

- [ ] **Step 5: Commit**

```bash
git add requirements-docker.txt Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: Dockerfile multi-stage + compose + dockerignore (D-2, D-7, D-9)"
```

---