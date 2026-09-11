### Task 7: Build & verifikasi end-to-end (Definition of Done spec §7)

**Files:** tidak ada yang dibuat — murni eksekusi verifikasi.

- [ ] **Step 1: Build image**

```bash
cd /Users/wayeien/Documents/firmware_transcribe
docker build --platform linux/amd64 -t mesin-transcribe .
```
Expected: build sukses; catat ukuran image (`docker images mesin-transcribe`) — target ~1.3–1.5 GB; jika jauh lebih besar, investigasi layer (kandidat: ctranslate2 + deps).

- [ ] **Step 2: Unit test in-container**

```bash
docker run --rm --platform linux/amd64 mesin-transcribe \
  python -m pytest tests/test_paths.py tests/test_config.py \
  tests/test_engine_paths.py tests/test_ai_flag.py tests/test_wdac_patch.py -q
```
Expected: semua PASS di Linux. (`test_engine_smoke.py`/`test_web.py` butuh model ter-download — dijalankan opsional dengan volume models ter-mount.)

- [ ] **Step 3: E2E transcribe**

```bash
docker compose up -d
# tunggu healthy: docker compose ps
curl -s http://localhost:8765/healthz        # {"ok":true}
curl -s http://localhost:8765/api/env | python3 -m json.tool
```
Expected `/api/env`: `ffmpeg.ok=true`, `ai_enabled=false`, `output_dir=/data/hasil`.
Lanjut upload + transcribe sample via API:

```bash
docker cp sample_audio/sample_75s.mp3 mesin-transcribe:/tmp/ || true
curl -s -F "file=@sample_audio/sample_75s.mp3" http://localhost:8765/api/upload
curl -s -X POST http://localhost:8765/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"audio_path":"/data/uploads/sample_75s.mp3","model":"small","language":"id"}'
# poll: curl -s http://localhost:8765/api/jobs/<id>
```
Expected: job selesai; `data/hasil/01_sample_75s/transkrip.txt` + `transkrip.json` ada **di host** (bukan hanya di container).

- [ ] **Step 4: AI off behavior**

```bash
curl -s -X POST http://localhost:8765/api/notulen/ai \
  -H "Content-Type: application/json" -d '{"output_dir":"01_sample_75s"}'
```
Expected: HTTP 503, detail mengandung "dimatikan". Di browser `http://localhost:8765`: badge "AI notulen nonaktif", tombol 🤖 disabled.

- [ ] **Step 5: Persistence**

```bash
docker compose down && docker compose up -d
```
Expected: `/api/history` masih menampilkan `01_sample_75s`; model tidak download ulang (cek log: tidak ada download progress); `data/config/config.json` ada di host setelah 1x transcribe.

- [ ] **Step 6: Commit docs deploy**

Buat `DEPLOY.md` singkat (cara build, up, ganti port, aktifkan AI, bersih-bersih uploads) lalu:

```bash
git add DEPLOY.md
git commit -m "docs: DEPLOY.md — runbook btd-server"
```

---

## Self-Review Log

- **Spec coverage:** D-1..D-10 → Task 6 (D-2,D-7,D-9), Task 1-4 (D-5, path/config), existing (D-3,D-4,D-6 tidak butuh kode baru). §6 error handling → Task 4 (503), Task 7 (verifikasi). §7 DoD → Task 7 1:1. §9 rollback → tidak butuh task (aditif by design). §10 rekomendasi → out of scope. ✅
- **Placeholder scan:** tidak ada TBD/"appropriate handling"; semua code block berisi kode aktual. ✅
- **Type consistency:** `UPLOAD_DIR`/`HASIL_DIR` bertipe `Path` di semua task; `AI_ENABLED: bool`; response key `ai_enabled` konsisten antara Task 4 (server) dan Task 5 (frontend); `/healthz` konsisten antara Task 4 (endpoint) dan Task 6 (HEALTHCHECK). ✅
- **Catatan risiko eksekusi:** `importlib.reload` pada modul yang memakai `from x import y` (mis. `server.py` meng-import `HASIL_DIR` by-name) bisa menyisakan referensi lama di modul lain — test di Task 4 hanya me-reload `server.py` + dependencies-nya yang relevan; jika flaky, restart interpreter per test (pytest process per file sudah cukup karena urutan file terpisah).