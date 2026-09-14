#!/usr/bin/env bash
# verify_deploy.sh — Verifikasi deployment Mesin Transcribe di btd-server.
# Menjalankan seluruh DoD spec §7 secara berurutan.
# Idempotent: aman dijalankan ulang (data/ TIDAK dihapus).
set -euo pipefail

cd "$(dirname "$0")"

BASE_URL="http://localhost:${TRANSCRIBE_HOST_PORT:-8765}/transcribe"
SAMPLE="sample_audio/sample_75s.mp3"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
PASSED=0

# ── Helper ────────────────────────────────────────────────────────────────
pass() { echo "  [PASS] $1"; PASSED=$((PASSED + 1)); }
gagal() {
    echo ""
    echo "  [GAGAL] $1" >&2
    echo "Verifikasi berhenti. Periksa pesan di atas, lalu jalankan ulang script." >&2
    echo "Log container: ${DC[*]} logs --tail=100" >&2
    exit 1
}

tunggu_healthy() {
    # Poll /healthz sampai 60 detik
    local i
    for i in $(seq 1 60); do
        if curl -sf "$BASE_URL/healthz" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# docker compose (plugin) atau docker-compose (legacy)
if docker compose version >/dev/null 2>&1; then
    DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    DC=(docker-compose)
else
    echo "GAGAL: docker compose tidak ditemukan." >&2
    exit 1
fi

echo "════════════════════════════════════════════════════════════════"
echo "  Verifikasi Deployment Mesin Transcribe — DoD spec §7"
echo "════════════════════════════════════════════════════════════════"

# Bersihkan container lama dulu (idempotent; data/ tetap aman)
"${DC[@]}" down >/dev/null 2>&1 || true

# ── Langkah 1: Build image ────────────────────────────────────────────────
echo ""
echo "── Langkah 1/7: Build image Docker ──"
docker build --platform "$DOCKER_PLATFORM" -t mesin-transcribe . || gagal "docker build gagal."
pass "Image mesin-transcribe berhasil dibangun"

# ── Langkah 2: Unit test in-container ─────────────────────────────────────
echo ""
echo "── Langkah 2/7: Unit test di dalam container ──"
docker run --rm mesin-transcribe \
    python -m pytest tests/ -x -q \
    || gagal "Unit test in-container gagal."
pass "Semua unit test PASS di dalam container"

# ── Langkah 3: compose up + tunggu healthy ────────────────────────────────
echo ""
echo "── Langkah 3/7: docker compose up + tunggu healthy (maks 60 detik) ──"
"${DC[@]}" up -d || gagal "docker compose up -d gagal."
tunggu_healthy || gagal "Server tidak sehat dalam 60 detik ($BASE_URL/healthz)."
pass "Server sehat di $BASE_URL"

# ── Langkah 4: Cek /api/env ───────────────────────────────────────────────
echo ""
echo "── Langkah 4/7: Cek /api/env ──"
curl -sf "$BASE_URL/api/env" -o /tmp/mt_env.json || gagal "GET /api/env gagal."
python3 - /tmp/mt_env.json <<'PYEOF' || gagal "/api/env tidak sesuai ekspektasi (ffmpeg.ok=true, ai_enabled=false, output_dir=/data/hasil)."
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  ffmpeg.ok   = {d['ffmpeg']['ok']}")
print(f"  ai_enabled  = {d['ai_enabled']}")
print(f"  output_dir  = {d['output_dir']}")
assert d["ffmpeg"]["ok"] is True, "ffmpeg.ok harus true"
assert d["ai_enabled"] is False, "ai_enabled harus false (default D-5)"
assert d["output_dir"] == "/data/hasil", "output_dir harus /data/hasil"
PYEOF
pass "/api/env sesuai ekspektasi"

# ── Langkah 5: E2E transcribe ─────────────────────────────────────────────
echo ""
echo "── Langkah 5/7: E2E transcribe sample_75s.mp3 (model medium, bahasa id) ──"
[ -f "$SAMPLE" ] || gagal "File sample tidak ditemukan: $SAMPLE"

curl -sf -F "file=@$SAMPLE" "$BASE_URL/api/upload" -o /tmp/mt_upload.json \
    || gagal "Upload gagal."
AUDIO_PATH=$(python3 -c "import json;print(json.load(open('/tmp/mt_upload.json'))['path'])")
echo "  Upload OK: $AUDIO_PATH"

curl -sf -X POST "$BASE_URL/api/transcribe" \
    -H "Content-Type: application/json" \
    -d "{\"audio_path\":\"$AUDIO_PATH\",\"model\":\"medium\",\"language\":\"id\"}" \
    -o /tmp/mt_job.json || gagal "POST /api/transcribe gagal."
JOB_ID=$(python3 -c "import json;print(json.load(open('/tmp/mt_job.json'))['id'])")
echo "  Job dibuat: $JOB_ID"
echo "  Menunggu job selesai (maks 30 menit — termasuk download model ~460MB pertama kali)..."

STATUS=""
SECS=0
while [ $SECS -lt 1800 ]; do
    curl -sf "$BASE_URL/api/jobs/$JOB_ID" -o /tmp/mt_status.json || gagal "GET /api/jobs/$JOB_ID gagal."
    STATUS=$(python3 -c "import json;print(json.load(open('/tmp/mt_status.json'))['status'])")
    case "$STATUS" in
        done|finished) break ;;
        error|cancelled)
            ERR=$(python3 -c "import json;print(json.load(open('/tmp/mt_status.json')).get('error'))")
            gagal "Job berakhir dengan status '$STATUS': $ERR"
            ;;
    esac
    sleep 10
    SECS=$((SECS + 10))
done
[ "$STATUS" = "done" ] || [ "$STATUS" = "finished" ] \
    || gagal "Timeout 30 menit menunggu job (status terakhir: $STATUS)."
echo "  Job selesai dalam ~${SECS} detik."

# Verifikasi output ada DI HOST: folder XX_sample_75s* terbaru di data/hasil/
# Cari hasil terbaru tanpa ketergantungan pada opsi ls GNU/BSD.
FOLDER=$(python3 - <<'PYEOF'
from pathlib import Path
folders = [p for p in Path("data/hasil").glob("*_sample_75s*") if p.is_dir()]
folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
print(str(folders[0]) + "/" if folders else "")
PYEOF
)
[ -n "$FOLDER" ] || gagal "Folder hasil *_sample_75s tidak ditemukan di data/hasil/ (host)."
[ -f "${FOLDER}transkrip.txt" ] || gagal "transkrip.txt tidak ada di $FOLDER"
[ -f "${FOLDER}transkrip.json" ] || gagal "transkrip.json tidak ada di $FOLDER"
pass "transkrip.txt + transkrip.json ada di host ($FOLDER)"
echo ""
echo "── Langkah 6/7: AI notulen harus nonaktif (HTTP 503) ──"
HTTP_CODE=$(curl -s -o /tmp/mt_ai.json -w "%{http_code}" \
    -X POST "$BASE_URL/api/notulen/ai" \
    -H "Content-Type: application/json" \
    -d '{"output_dir":"01_sample_75s"}')
[ "$HTTP_CODE" = "503" ] || gagal "POST /api/notulen/ai return HTTP $HTTP_CODE (ekspektasi 503)."
echo "  HTTP 503, detail: $(cat /tmp/mt_ai.json)"
python3 - <<'PYEOF' /tmp/mt_ai.json || gagal "Response /api/notulen/ai tidak mengandung kata 'dimatikan'."
import json, sys
assert "dimatikan" in json.load(open(sys.argv[1])).get("detail", "")
PYEOF
# ── Langkah 7: Persistence setelah restart ────────────────────────────────
echo ""
echo "── Langkah 7/7: Persistence setelah compose down/up ──"
"${DC[@]}" down || gagal "docker compose down gagal."
"${DC[@]}" up -d || gagal "docker compose up -d (kedua) gagal."
tunggu_healthy || gagal "Server tidak sehat setelah restart."

curl -sf "$BASE_URL/api/history" -o /tmp/mt_history.json || gagal "GET /api/history gagal."
python3 - /tmp/mt_history.json <<'PYEOF' || gagal "/api/history tidak menampilkan folder sample_75s setelah restart."
import json, sys
d = json.load(open(sys.argv[1]))
names = [i["name"] for i in d["items"]]
print(f"  History: {names}")
assert any("sample_75s" in n for n in names), "folder sample_75s tidak ada di history"
PYEOF

[ -f data/config/config.json ] || gagal "data/config/config.json tidak ada di host."
pass "History persist + data/config/config.json ada di host"

# ── Selesai ───────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  SEMUA VERIFIKASI LULUS (7/7 langkah)"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Deployment siap dipakai:"
echo "  • Buka dashboard : $BASE_URL"
echo "  • Stop server    : ${DC[*]} down"
echo "  • Lihat log      : ${DC[*]} logs -f"
echo "  • Hasil transkrip: ./data/hasil/"
echo ""
