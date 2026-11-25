"""AI Notulen Generator — rangkum transkrip via LLM lokal (9router).

Alur: baca transkrip (TXT + JSON) dari folder hasil → kirim ke router lokal
(OpenAI-compatible) → notulen Markdown → render ke DOCX via
MdToDocx.from_text dan PDF via Typst bila CLI tersedia. Markdown resmi
juga disimpan sebagai output terpisah.

Konfigurasi (env var, bisa di .env project):
    TRANSCRIBE_AI_BASE_URL   default http://localhost:20128/v1
    TRANSCRIBE_AI_MODEL      default gemini/gemini-3.7-flash
    TRANSCRIBE_AI_API_KEY    default "" (9router lokal tanpa key)

Callback contract (dipanggil dari thread worker):
    on_log(message)
    on_progress(percent, message)
    on_finished(result: dict)
    on_error(error)
"""

import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from src.core.engine import CancelledError
from src.pandora_documents import render as render_naskah
from src.pandora_documents.render import PerkakasTidakTersedia
from src.utils.ai_notice import CATATAN_AI, aturan_terjemahan

AI_BASE_URL = os.environ.get("TRANSCRIBE_AI_BASE_URL", "http://localhost:20128/v1")
AI_MODEL = os.environ.get("TRANSCRIBE_AI_MODEL", "gemini/gemini-3.7-flash")
AI_API_KEY = os.environ.get("TRANSCRIBE_AI_API_KEY", "")

MAX_INPUT_CHARS = 180_000  # transkrip lebih panjang dipotong (model 1M context, ini batas hemat)
MAX_OUTPUT_TOKENS = 8192
# Merapikan berarti menulis ulang seluruh transkrip, jadi keluarannya sepanjang
# masukannya. Transkrip dirapikan per potongan supaya tiap jawaban muat di bawah
# batas keluaran model.
CLEANUP_CHUNK_CHARS = 12_000


class OutputTruncatedError(ValueError):
    """Jawaban model berhenti di batas keluaran, jadi isinya tidak utuh."""


_server_log = logging.getLogger("pandora.ai")


def ai_config() -> dict:
    """Konfigurasi AI saat ini. Hanya untuk sisi server: JANGAN dikirim ke browser atau dicatat di log proses."""
    return {"base_url": AI_BASE_URL, "model": AI_MODEL, "key_set": bool(AI_API_KEY)}


def check_ai_router(timeout: float = 2.0) -> dict:
    """Probe endpoint model router tanpa mengirim isi transkrip."""
    url = f"{AI_BASE_URL.rstrip('/')}/models"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {AI_API_KEY}"} if AI_API_KEY else {})
        return {
            "reachable": True,
            "ok": response.is_success,
            "status_code": response.status_code,
            "error": None if response.is_success else f"HTTP {response.status_code}",
        }
    except (httpx.HTTPError, ValueError) as exc:
        _server_log.warning("Pemeriksaan layanan AI gagal (%s): %s", AI_BASE_URL, exc)
        return {"reachable": False, "ok": False, "status_code": None, "error": "tidak terhubung"}


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


HEARTBEAT_LOG_SECONDS = 15
PROGRESS_TICK_SECONDS = 2
KARAKTER_PER_DETIK = 1300     # perkiraan kasar laju AI; hanya dipakai untuk membentuk kurva progres


def perkiraan_progres(detik: float, karakter: int, awal: int, akhir: int) -> int:
    """Persen perkiraan selama menunggu AI: naik cepat lalu melambat, tidak pernah menyentuh batas atas.

    Kurva 1 - e^(-t/tau) dengan tau mengikuti besar masukan, jadi masukan besar naik lebih pelan.
    Angka asli baru diketahui saat respons tiba, maka persen ini perkiraan dan ditandai demikian.
    """
    tau = max(15.0, min(karakter / KARAKTER_PER_DETIK, 300.0))
    return int(awal + (akhir - awal) * (1 - math.exp(-max(detik, 0.0) / tau)))


def _tanya_ai(system: str, user: str, cancel_event, log, label: str,
              progress=None, rentang: tuple = (25, 78)) -> str:
    """Panggil AI sambil melaporkan kemajuan: persen perkiraan, catatan lama menunggu, dan ringkasan respons.

    Panggilan AI bisa memakan beberapa menit tanpa keluaran; tanpa laporan berkala, bar dan log tampak macet.
    """
    mulai = time.time()
    selesai = threading.Event()

    def denyut():
        terakhir_log = mulai
        while not selesai.wait(PROGRESS_TICK_SECONDS):
            detik = time.time() - mulai
            if progress:
                progress(perkiraan_progres(detik, len(user), *rentang),
                         f"AI sedang bekerja · {int(detik)} detik · persentase perkiraan")
            if time.time() - terakhir_log >= HEARTBEAT_LOG_SECONDS:
                terakhir_log = time.time()
                log(f"{label}: masih menunggu respons AI ({int(detik)} detik)...")

    pengetuk = threading.Thread(target=denyut, daemon=True, name="ai-heartbeat")
    pengetuk.start()
    try:
        teks = call_llm(system, user) if cancel_event is None else call_llm(system, user, cancel_event=cancel_event)
    finally:
        selesai.set()
    log(f"{label}: respons diterima ({len(teks):,} karakter, {time.time() - mulai:.0f} detik).")
    return teks


def call_llm(system: str, user: str, cancel_event=None) -> str:
    """Panggil router lokal (OpenAI-compatible) — non-streaming, retry 1x."""
    url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
    }

    last_err = None
    kode_http = None
    for attempt in (1, 2):
        _check_cancel(cancel_event)
        try:
            with httpx.Client(timeout=600.0) as client:
                r = client.post(url, headers=headers, json=payload)
            _check_cancel(cancel_event)
            if r.status_code == 200:
                data = r.json()
                choice = (data.get("choices") or [{}])[0]
                content = choice.get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise ValueError("Respons LLM kosong.")
                if choice.get("finish_reason") == "length":
                    raise OutputTruncatedError(
                        "Jawaban AI terpotong pada batas keluaran model, sehingga hasilnya tidak utuh. "
                        "Hasil tidak disimpan."
                    )
                return content.strip()
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
            kode_http = r.status_code
        except httpx.HTTPError as e:
            last_err = f"koneksi gagal: {e}"
        time.sleep(1.5)

    # Rincian (model, alamat layanan, isi galat) hanya masuk log server; pengguna cukup melihat pesan umum.
    _server_log.error("Panggilan AI gagal (%s @ %s): %s", AI_MODEL, AI_BASE_URL, last_err)
    raise ConnectionError(
        "Layanan AI tidak dapat dihubungi" + (f" (kode {kode_http})" if kode_http else "")
        + ". Pastikan layanan AI berjalan, lalu coba lagi."
    )
def load_transcript(output_dir: str) -> tuple:
    """Baca transkrip dari folder hasil.

    Returns (full_text, meta). Sumber: transkrip.txt; fallback transkrip.json
    (gabung segmen). Meta: {source_name, audio_duration}.
    """
    out = Path(output_dir)
    txt = out / "transkrip.txt"
    js = out / "transkrip.json"

    meta = {"source_name": out.name, "audio_duration": None, "language": None}

    # JSON dibaca juga saat TXT ada: durasi audio hanya tercatat di sana.
    data = None
    if js.is_file():
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
        except ValueError:
            data = None
    segs = data.get("segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    segs = [s for s in segs if isinstance(s, dict)]
    if isinstance(data, dict):
        meta["language"] = data.get("language")
    if isinstance(data, dict) and data.get("audio_duration_s"):
        meta["audio_duration"] = data["audio_duration_s"]
    elif segs:
        # Hasil lama tidak menyimpan durasi; akhir segmen terakhir adalah perkiraan terdekat.
        try:
            meta["audio_duration"] = round(float(segs[-1].get("end") or 0), 1) or None
        except (TypeError, ValueError):
            pass

    if txt.is_file():
        full_text = txt.read_text(encoding="utf-8").strip()
    elif data is not None:
        full_text = " ".join(str(s.get("text", "")).strip() for s in segs).strip()
    else:
        raise FileNotFoundError(
            f"transkrip.txt / transkrip.json tidak ditemukan di {output_dir}. "
            "Transkripsikan audio dulu sebelum membuat notulen AI."
        )

    if not full_text:
        raise ValueError("Transkrip kosong — tidak bisa membuat notulen AI.")

    return full_text, meta


def build_prompt(full_text: str, meta: dict) -> tuple:
    """Bangun (system, user) prompt. Transkrip panjang dipotong + ditandai."""
    truncated = False
    text = full_text
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
        truncated = True

    system = (
        "Kamu adalah notulis profesional untuk rapat, kick-off program, dan forum teknis. "
        "Ubah transkrip mentah menjadi notulen terstruktur dengan gaya dokumen "
        "AITF Batch 2 — Notulen Detail: formal, berbasis bukti, mudah diaudit, "
        "dan tidak mengarang informasi."
    )

    terjemahan = aturan_terjemahan(meta.get("language"))
    terjemahan = f"\n   {terjemahan}" if terjemahan else ""
    dur_str = meta["audio_duration"] if meta["audio_duration"] is not None else "tidak diketahui"
    trunc_note = "CATATAN: transkrip asli lebih panjang dari batas, hanya bagian awal yang dikirim.\n" if truncated else ""

    user = f"""Ubahlah transkrip rapat berikut menjadi notulen yang rapi, terstruktur, dan jelas.

ATURAN:
1. Tulis dalam Bahasa Indonesia formal dan mudah dibaca.{terjemahan}
2. Ikuti struktur dokumen berikut bila informasinya tersedia. Jangan membuat bagian kosong:
   # Notulen [judul rapat/program]
   - tanggal, waktu, format/lokasi, durasi sumber, dan catatan kualitas ASR
   ## 1. Ringkasan Eksekutif
   ## 2. Pihak/Lembaga yang Hadir
   ### Pembicara/Pimpinan yang Disebut
   ## 3. Urutan Agenda dan Poin Utama
   ### 3.1 [Agenda/topik]
   ### 3.2 [Agenda/topik]
   ## 4. Topik/Use Case Utama
   ### 4.1 [Topik]
   ## 5. Gap/Kesenjangan yang Teridentifikasi
   ## 6. Governance Data, Privasi, dan Prasyarat
   ## 7. Action Items
   Gunakan tabel Markdown: | Prioritas | Action / Deliverable | Owner | Target | Status |
   Isi Owner, Target, dan Status hanya jika disebut atau dapat disimpulkan langsung; jika tidak, gunakan "Belum ditentukan".
   ## 8. Keputusan/Arah yang Perlu Dijaga
   ## 9. Risiko dan Isu Terbuka
   ## 10. Kesimpulan
   ### Sumber dan Catatan Kualitas
3. HANYA gunakan informasi yang ada di transkrip. JANGAN menambah, menebak, atau mengarang
   nama, jabatan, angka, tanggal, keputusan, owner, deadline, status, atau fakta apa pun. Bagian yang tidak jelas atau terpotong tulis "[tidak jelas]" dan tandai bahwa verifikasi sumber resmi diperlukan.
4. Bedakan secara eksplisit antara fakta yang diucapkan, usulan, keputusan, risiko, dan isu terbuka. Jangan mengubah usulan menjadi keputusan.
5. Ringkas poin penting — jangan menyalin seluruh transkrip kata demi kata.
6. Format output Markdown ringan: # untuk judul, ##/### untuk bagian, - untuk poin, tabel untuk action items. Jangan menulis penjelasan di luar isi notulen.

Informasi berkas:
- Nama berkas audio: {meta['source_name']}
- Durasi audio: {dur_str} detik
{trunc_note}=== MULAI TRANSKRIP ===
{text}
=== AKHIR TRANSKRIP ===
"""
    return system, user


def _audio_context(source_name: str, text: str) -> str:
    """Infer a conservative prompt context from filename and transcript cues."""
    value = f"{source_name} {text[:4000]}".lower()
    if any(word in value for word in ("wawancara", "narasumber", "interview", "interviewer")):
        return "wawancara"
    if any(word in value for word in ("kuliah", "materi", "presentasi", "paparan", "seminar")):
        return "kuliah atau paparan"
    if any(word in value for word in ("voice note", "voicenote", "catatan suara", "pesan suara")):
        return "voice note"
    if any(word in value for word in ("rapat", "meeting", "diskusi", "agenda", "keputusan")):
        return "rapat atau diskusi"
    return "rekaman percakapan umum"


def split_transcript(text: str, size: int = CLEANUP_CHUNK_CHARS) -> list:
    """Bagi transkrip menjadi potongan berurutan tanpa memotong di tengah kalimat.

    Seluruh teks tercakup: gabungan potongan sama dengan teks asal.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            # Mundur ke akhir kalimat terdekat; bila tidak ada, ke spasi terdekat.
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "), window.rfind("\n"))
            if cut < size // 2:
                cut = window.rfind(" ")
            if cut > 0:
                end = start + cut + 1
        chunks.append(text[start:end])
        start = end
    return chunks or [""]


def build_cleanup_prompt(full_text: str, meta: dict, part: tuple | None = None,
                         context: str | None = None) -> tuple:
    """Build a context-aware prompt that cleans transcript without inventing facts.

    `part=(urutan, jumlah)` menandai bahwa teks ini satu potongan dari transkrip
    yang lebih panjang; `context` adalah konteks audio yang dideteksi dari
    transkrip utuh.
    """
    text = full_text[:MAX_INPUT_CHARS]
    context = context or _audio_context(meta.get("source_name", ""), full_text)
    truncated = "" if len(full_text) <= MAX_INPUT_CHARS else "\nCATATAN: transkrip dipotong setelah batas karakter."
    if part and part[1] > 1:
        truncated += (
            f"\nCATATAN: ini bagian {part[0]} dari {part[1]} bagian transkrip yang berurutan. "
            "Rapikan bagian ini saja dan lanjutkan apa adanya; jangan menulis pembuka, penutup, "
            "judul dokumen, atau ringkasan."
        )
    terjemahan = aturan_terjemahan(meta.get("language"))
    aturan_bahasa = f"\n7. {terjemahan}" if terjemahan else ""
    system = (
        "Kamu adalah editor transkrip profesional. Tugasmu merapikan transkrip mentah "
        "agar mudah dibaca tanpa mengubah makna, fakta, urutan, atau siapa yang berbicara."
    )
    user = f"""Rapikan transkrip audio berikut. Konteks rekaman terdeteksi sebagai: {context}.

ATURAN:
1. Hapus filler yang tidak bermakna (misalnya 'eee', 'emm', pengulangan pendek) dan perbaiki tanda baca.
2. Pertahankan semua informasi, angka, nama, keputusan, keraguan, dan urutan pembicaraan.
3. JANGAN mengubah makna: jangan meringkas, menambah, atau menebak. Jika bagian tidak jelas, tulis [tidak jelas].
4. Pertahankan pergantian pembicara jika dapat dikenali. Jangan membuat nama pembicara yang tidak ada.
5. Gunakan paragraf dan heading seperlunya sesuai konteks audio; untuk wawancara gunakan format pembicara yang jelas.
6. Hasil hanya teks transkrip yang sudah dirapikan, tanpa pengantar atau komentar editor.{aturan_bahasa}

Informasi berkas:
- Nama sumber: {meta.get('source_name', 'tidak diketahui')}
- Durasi audio: {meta.get('audio_duration', 'tidak diketahui')} detik
{truncated}
=== MULAI TRANSKRIP ===
{text}
=== AKHIR TRANSKRIP ===
"""
    return system, user

def generate_cleanup(output_dir: str, callbacks: dict = None, cancel_event=None) -> dict:
    """Rapikan transkrip dengan AI dan simpan TXT hasil tanpa mengubah sumber."""
    cb = callbacks or {}
    cancel_event = cancel_event or cb.get("cancel_event")

    def log(msg):
        if cb.get("on_log"):
            cb["on_log"](msg)

    def progress(pct, msg):
        if cb.get("on_progress"):
            cb["on_progress"](pct, msg)

    start = time.time()
    _check_cancel(cancel_event)
    log("AI rapikan: membaca transkrip...")
    full_text, meta = load_transcript(output_dir)
    log(f"AI rapikan: {len(full_text):,} karakter dari {meta['source_name']}.")
    progress(15, "Menyusun prompt sesuai konteks audio...")
    context = _audio_context(meta.get("source_name", ""), full_text)
    log(f"AI rapikan: konteks audio terdeteksi sebagai {context}.")
    chunks = split_transcript(full_text)
    if len(chunks) > 1:
        log(f"AI rapikan: {len(full_text):,} karakter dirapikan dalam {len(chunks)} bagian.")
    log("AI rapikan: mengirim transkrip ke layanan AI — ini bisa memakan beberapa menit.")
    cleaned_parts = []
    for index, chunk in enumerate(chunks, 1):
        _check_cancel(cancel_event)
        system, user = build_cleanup_prompt(chunk, meta, part=(index, len(chunks)), context=context)
        if len(chunks) == 1:
            progress(25, "Memanggil AI...")
        else:
            progress(25 + int(55 * (index - 1) / len(chunks)),
                     f"Merapikan bagian {index} dari {len(chunks)}...")
        label = "AI rapikan" if len(chunks) == 1 else f"AI rapikan bagian {index}/{len(chunks)}"
        awal = 25 + int(55 * (index - 1) / len(chunks))
        akhir = 25 + int(55 * index / len(chunks)) - 2
        cleaned_parts.append(_tanya_ai(system, user, cancel_event, log, label,
                                       progress=progress, rentang=(awal, akhir)))
    cleaned = "\n\n".join(part.strip() for part in cleaned_parts) + "\n\n" + CATATAN_AI
    _check_cancel(cancel_event)
    progress(85, "Menyimpan transkrip rapi...")
    out = Path(output_dir)
    md_path = out / "transkrip_rapi_ai.md"
    md_header = (
        f"# Transkrip Rapi AI — {meta['source_name']}\n\n"
        f"- Konteks: {context}\n"
        "- Catatan: hasil AI perlu ditinjau manual.\n\n"
    )
    md_content = md_header + cleaned.strip() + "\n"
    md_path.write_text(md_content, encoding="utf-8")
    log(f"AI rapikan: MD -> {Path(str(md_path)).name}")
    safe_stem = re.sub(r"[^\w\- ]", "", meta["source_name"]).strip()[:50] or "transkrip"
    docx_path = out / f"TranskripRapiAI_{safe_stem}.docx"
    # Tampilan yang sama dengan dokumen resmi, tanpa ruang tanda tangan; Markdown sumber tidak diubah.
    naskah = render_naskah.naskah_dari_markdown(
        "\n\n".join(part.strip() for part in cleaned_parts) + "\n", nama_jenis="Transkrip Rapi", penanda_tangan=None,
        judul=meta["source_name"], kepala=[("Sumber", meta["source_name"]), ("Konteks", context)],
        catatan=CATATAN_AI)
    render_naskah.bentuk_docx(naskah, docx_path)
    log(f"AI rapikan: DOCX -> {Path(str(docx_path)).name}")
    txt_path = out / "transkrip_rapi_ai.txt"
    header = (
        f"TRANSKRIP RAPI AI — {meta['source_name']}\n"
        f"Konteks: {context}\n"
        "Catatan: hasil AI perlu ditinjau manual.\n" + "=" * 60 + "\n\n"
    )
    txt_path.write_text(header + cleaned.strip() + "\n", encoding="utf-8")
    log(f"AI rapikan: TXT -> {Path(str(txt_path)).name}")
    result = {"md_path": str(md_path), "txt_path": str(txt_path), "docx_path": str(docx_path),
              "context": context, "chars_in": len(full_text),
              "duration_s": round(time.time() - start, 1)}
    progress(100, "Transkrip rapi selesai.")
    log(f"AI rapikan selesai dalam {result['duration_s']}s.")
    if cb.get("on_finished"):
        cb["on_finished"](result)
    return result




def normalize_notulen_markdown(text: str) -> str:
    """Bersihkan placeholder [[label]] yang kadang lolos dari respons AI."""
    # [[Tanggal:]] Nilai -> Tanggal: Nilai; tidak mengubah isi faktual.
    text = re.sub(r"\[\[\s*([^\]]+?)\s*\]\]\s*", r"\1 ", text)
    # Placeholder kosong yang tersisa tidak boleh tampil di output publik.
    text = re.sub(r"\[\[.*?\]\]", "", text)
    return re.sub(r"[ \t]+", " ", text).replace(" \n", "\n").strip()


def _md_to_plain(text: str) -> str:
    """Strip markdown syntax ringan untuk file preview .txt."""
    t = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)      # heading
    t = re.sub(r"^\s*[-*]\s+", "- ", t, flags=re.MULTILINE)       # bullet
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)        # numbered
    t = re.sub(r"\|", " | ", t)                                    # table pipes
    t = re.sub(r"^[\s|:-]+$", "", t, flags=re.MULTILINE)           # table separator
    t = re.sub(r"[*_`~]", "", t)                                   # inline
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                 # links
    return t.strip()

def generate_notulen_docx(output_dir: str, callbacks: dict = None, cancel_event=None) -> dict:
    """Buat notulen AI dari transkrip di output_dir → simpan DOCX + TXT preview.

    Returns {"docx_path", "txt_path", "chars_in", "duration_s", "truncated"}
    """
    cb = callbacks or {}
    cancel_event = cancel_event or cb.get("cancel_event")

    def log(msg):
        if cb.get("on_log"):
            cb["on_log"](msg)

    def progress(pct, msg):
        if cb.get("on_progress"):
            cb["on_progress"](pct, msg)

    try:
        _check_cancel(cancel_event)
        start = time.time()
        log("AI notulen: membaca transkrip...")
        full_text, meta = load_transcript(output_dir)
        log(f"AI notulen: {len(full_text):,} karakter dari {meta['source_name']}.")

        progress(15, "Menyusun prompt...")
        system, user = build_prompt(full_text, meta)
        truncated = "CATATAN: transkrip asli lebih panjang" in user

        progress(25, "Memanggil AI...")
        log("AI notulen: mengirim transkrip ke layanan AI — ini bisa memakan beberapa menit.")
        if truncated:
            log("AI notulen: peringatan, transkrip lebih panjang dari batas; hanya bagian awal yang dikirim.")
        notulen_md = normalize_notulen_markdown(
            _tanya_ai(system, user, cancel_event, log, "AI notulen", progress=progress, rentang=(25, 78)))
        notulen_isi = notulen_md.strip() + "\n"          # untuk DOCX/PDF: catatan AI dicetak sebagai catatan kaki
        notulen_md = notulen_md.rstrip() + "\n\n" + CATATAN_AI + "\n"
        _check_cancel(cancel_event)

        progress(80, "Merender DOCX...")
        out = Path(output_dir)
        stem = meta["source_name"]
        m = re.match(r"^\d{2,}_(.+)$", stem)
        if m:
            stem = m.group(1)
        stem = re.sub(r"[^\w\- ]", "", stem).strip()[:50] or "notulen"

        # DOCX dan PDF memakai tampilan naskah dinas yang sama dengan dokumen resmi.
        naskah = render_naskah.naskah_dari_markdown(
            notulen_isi, nama_jenis="Notulen Rapat", penanda_tangan="Notulis", catatan=CATATAN_AI)
        if not naskah.judul or naskah.judul == "Tanpa judul":
            naskah.judul = meta["source_name"]
        docx_path = out / f"NotulenAI_{stem}.docx"
        render_naskah.bentuk_docx(naskah, docx_path)
        log(f"AI notulen: DOCX -> {Path(str(docx_path)).name}")

        md_path = out / "notulen_ai.md"
        md_header = (
            f"# Notulen AI — {meta['source_name']}\n\n"
            f"- Transkrip: {len(full_text):,} karakter\n"
            "- Catatan: ringkasan otomatis AI; review manual disarankan.\n\n"
        )
        md_path.write_text(md_header + notulen_md.strip() + "\n", encoding="utf-8")
        log(f"AI notulen: MD -> {Path(str(md_path)).name}")

        pdf_path = None
        try:
            progress(90, "Merender PDF dengan Typst...")
            pdf_path = render_naskah.bentuk_pdf(naskah, out / f"NotulenAI_{stem}.pdf")
            log(f"AI notulen: PDF -> {Path(str(pdf_path)).name}")
        except PerkakasTidakTersedia as exc:
            log(f"AI notulen: PDF dilewati ({exc})")
        except Exception as exc:  # PDF failure must not discard DOCX/MD/TXT outputs
            log(f"AI notulen: PDF gagal, output lain tetap tersedia ({exc})")
            pdf_path = None

        _check_cancel(cancel_event)

        txt_path = out / "notulen_ai.txt"
        plain = _md_to_plain(notulen_md)
        header = (
            f"NOTULEN AI — {meta['source_name']}\n"
            f"Dibuat: {datetime.now().strftime('%d %B %Y %H:%M')}\n"
            f"Transkrip: {len(full_text):,} karakter | Ringkasan otomatis AI — review manual disarankan.\n"
            + "=" * 60 + "\n\n"
        )
        txt_path.write_text(header + plain + "\n", encoding="utf-8")
        log(f"AI notulen: TXT -> {Path(str(txt_path)).name}")

        duration_s = round(time.time() - start, 1)
        result = {
            "docx_path": str(docx_path),
            "pdf_path": pdf_path,
            "md_path": str(md_path),
            "txt_path": str(txt_path),
            "chars_in": len(full_text),
            "duration_s": duration_s,
            "truncated": truncated,
        }
        progress(100, "Selesai.")
        log(f"AI notulen selesai dalam {duration_s}s.")
        if cb.get("on_finished"):
            cb["on_finished"](result)
        return result

    except CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        if cb.get("on_error"):
            cb["on_error"](str(e))
        raise
