### Task 4: `server.py` — UPLOAD_DIR dari paths + AI_ENABLED flag

**Files:**
- Modify: `src/web/server.py:29-33` (UPLOAD_DIR), `:38-42` (flag), `:58-69` (/api/env), `:166-182` (/api/notulen/ai)
- Test: `tests/test_ai_flag.py` (baru)

**Interfaces:**
- Consumes: `src.utils.paths.UPLOAD_DIR` (Task 1)
- Produces: module-level `AI_ENABLED: bool` di `server.py`; response `/api/env` bertambah key `ai_enabled: bool`; `POST /api/notulen/ai` mengembalikan HTTP 503 `{detail: str}` saat flag off. Task 5 (frontend) membaca `env.ai_enabled`.

- [ ] **Step 1: Tulis failing test**

Buat `tests/test_ai_flag.py`:

```python
"""Test feature flag AI_ENABLED pada server (Docker deployment)."""
import importlib
import os


def _make_client(monkeypatch, ai_enabled):
    monkeypatch.setenv("AI_ENABLED", ai_enabled)
    import src.web.server as server
    importlib.reload(server)
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_env_expose_ai_enabled_off(monkeypatch):
    client = _make_client(monkeypatch, "false")
    r = client.get("/api/env")
    assert r.status_code == 200
    assert r.json()["ai_enabled"] is False


def test_env_expose_ai_enabled_on(monkeypatch):
    client = _make_client(monkeypatch, "true")
    r = client.get("/api/env")
    assert r.json()["ai_enabled"] is True


def test_notulen_ai_503_saat_off(monkeypatch):
    client = _make_client(monkeypatch, "false")
    r = client.post("/api/notulen/ai", json={"output_dir": "01_test"})
    assert r.status_code == 503
    assert "dimatikan" in r.json()["detail"]
```

Catatan: test `notulen_ai` saat ON sengaja tidak ada di sini (sudah dicakup `test_web.py` existing yang menjalankan job AI asli via 9router — tidak tersedia di container; flag ON di container diverifikasi manual saja saat dibutuhkan).

- [ ] **Step 2: Jalankan test, verifikasi FAIL**

Run: `python3 -m pytest tests/test_ai_flag.py -v`
Expected: FAIL — `KeyError: 'ai_enabled'` dan status 400/404 bukan 503

- [ ] **Step 3: Implementasi**

Patch `src/web/server.py`:

(a) Baris 29-33 — UPLOAD_DIR dari paths:

```python
WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
from src.utils.paths import UPLOAD_DIR  # noqa: E402  (menghormati DATA_DIR)
```

(hapus `PROJECT_ROOT = WEB_DIR.parents[1]` dan `UPLOAD_DIR = PROJECT_ROOT / "uploads"`)

(b) Setelah baris 42 (`ALLOWED_EXT`), tambah:

```python
# Feature flag AI notulen (D-5): default off di deployment Docker
AI_ENABLED = os.environ.get("AI_ENABLED", "false").strip().lower() == "true"
```

(c) `/api/env` (baris 62-69) — tambah key:

```python
    return {
        "ffmpeg": ff,
        "model_cached": model_cached,
        "model_default": "small",
        "output_dir": str(HASIL_DIR),
        "ai": ai_config(),
        "ai_enabled": AI_ENABLED,
        "settings": load_config(),  # settings terakhir tersimpan (persistence)
    }
```

(d) `notulen_ai` — guard paling atas (setelah docstring, sebelum baca body):

```python
    if not AI_ENABLED:
        raise HTTPException(
            503,
            "Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)",
        )
```

(e) Tambahkan endpoint alias health untuk Docker HEALTHCHECK (tepat setelah route `/api/env`):

```python
@app.get("/healthz")
def healthz():
    return {"ok": True}
```

- [ ] **Step 4: Jalankan test, verifikasi PASS**

Run: `python3 -m pytest tests/test_ai_flag.py -v`
Expected: 3 PASS. Lalu regresi: `python3 -m pytest tests/test_paths.py tests/test_config.py tests/test_engine_paths.py -v` tetap PASS.

- [ ] **Step 5: Commit**

```bash
git add src/web/server.py tests/test_ai_flag.py
git commit -m "feat: AI_ENABLED feature flag + UPLOAD_DIR dari paths + /healthz"
```

---