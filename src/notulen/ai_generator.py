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

import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

from src.export.docx_converter import MdToDocx
from src.export.typst_converter import TypstUnavailableError, render_pdf

AI_BASE_URL = os.environ.get("TRANSCRIBE_AI_BASE_URL", "http://localhost:20128/v1")
AI_MODEL = os.environ.get("TRANSCRIBE_AI_MODEL", "gemini/gemini-3.7-flash")
AI_API_KEY = os.environ.get("TRANSCRIBE_AI_API_KEY", "")

MAX_INPUT_CHARS = 180_000  # transkrip lebih panjang dipotong (model 1M context, ini batas hemat)


def ai_config() -> dict:
    """Konfigurasi AI saat ini (dipakai /api/env + log)."""
    return {"base_url": AI_BASE_URL, "model": AI_MODEL, "key_set": bool(AI_API_KEY)}


def load_transcript(output_dir: str) -> tuple:
    """Baca transkrip dari folder hasil.

    Returns (full_text, meta). Sumber: transkrip.txt; fallback transkrip.json
    (gabung segmen). Meta: {source_name, audio_duration}.
    """
    out = Path(output_dir)
    txt = out / "transkrip.txt"
    js = out / "transkrip.json"

    meta = {"source_name": out.name, "audio_duration": None}

    if txt.is_file():
        full_text = txt.read_text(encoding="utf-8").strip()
    elif js.is_file():
        import json
        data = json.loads(js.read_text(encoding="utf-8"))
        segs = data.get("segments", data if isinstance(data, list) else [])
        full_text = " ".join(
            str(s.get("text", "")).strip() for s in segs if isinstance(s, dict)
        ).strip()
        meta["audio_duration"] = data.get("audio_duration_s") if isinstance(data, dict) else None
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

    dur_str = meta["audio_duration"] if meta["audio_duration"] is not None else "tidak diketahui"
    trunc_note = "CATATAN: transkrip asli lebih panjang dari batas, hanya bagian awal yang dikirim.\n" if truncated else ""

    user = f"""Ubahlah transkrip rapat berikut menjadi notulen yang rapi, terstruktur, dan jelas.

ATURAN:
1. Tulis dalam Bahasa Indonesia formal dan mudah dibaca.
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


def build_cleanup_prompt(full_text: str, meta: dict) -> tuple:
    """Build a context-aware prompt that cleans transcript without inventing facts."""
    text = full_text[:MAX_INPUT_CHARS]
    context = _audio_context(meta.get("source_name", ""), full_text)
    truncated = "" if len(full_text) <= MAX_INPUT_CHARS else "\nCATATAN: transkrip dipotong setelah batas karakter."
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
6. Hasil hanya teks transkrip yang sudah dirapikan, tanpa pengantar atau komentar editor.

Informasi berkas:
- Nama sumber: {meta.get('source_name', 'tidak diketahui')}
- Durasi audio: {meta.get('audio_duration', 'tidak diketahui')} detik
{truncated}
=== MULAI TRANSKRIP ===
{text}
=== AKHIR TRANSKRIP ===
"""
    return system, user


def generate_cleanup(output_dir: str, callbacks: dict = None) -> dict:
    """Rapikan transkrip dengan AI dan simpan TXT hasil tanpa mengubah sumber."""
    cb = callbacks or {}

    def log(msg):
        if cb.get("on_log"):
            cb["on_log"](msg)

    def progress(pct, msg):
        if cb.get("on_progress"):
            cb["on_progress"](pct, msg)

    start = time.time()
    full_text, meta = load_transcript(output_dir)
    progress(15, "Menyusun prompt sesuai konteks audio...")
    context = _audio_context(meta.get("source_name", ""), full_text)
    log(f"AI rapikan: konteks audio terdeteksi sebagai {context}.")
    system, user = build_cleanup_prompt(full_text, meta)
    progress(25, f"Memanggil AI ({AI_MODEL})...")
    cleaned = call_llm(system, user)
    progress(85, "Menyimpan transkrip rapi...")
    out = Path(output_dir)
    md_path = out / "transkrip_rapi_ai.md"
    md_header = (
        f"# Transkrip Rapi AI — {meta['source_name']}\n\n"
        f"- Model: `{AI_MODEL}`\n"
        f"- Konteks: {context}\n"
        "- Catatan: hasil AI perlu ditinjau manual.\n\n"
    )
    md_content = md_header + cleaned.strip() + "\n"
    md_path.write_text(md_content, encoding="utf-8")
    safe_stem = re.sub(r"[^\w\- ]", "", meta["source_name"]).strip()[:50] or "transkrip"
    docx_path = out / f"TranskripRapiAI_{safe_stem}.docx"
    # Reuse the existing Markdown-to-DOCX renderer; source Markdown remains intact.
    MdToDocx.from_text(md_content, str(docx_path))
    txt_path = out / "transkrip_rapi_ai.txt"
    header = (
        f"TRANSKRIP RAPI AI — {meta['source_name']}\n"
        f"Model: {AI_MODEL} | Konteks: {context}\n"
        "Catatan: hasil AI perlu ditinjau manual.\n" + "=" * 60 + "\n\n"
    )
    txt_path.write_text(header + cleaned.strip() + "\n", encoding="utf-8")
    result = {"md_path": str(md_path), "txt_path": str(txt_path), "docx_path": str(docx_path), "model": AI_MODEL,
              "context": context, "chars_in": len(full_text),
              "duration_s": round(time.time() - start, 1)}
    progress(100, "Transkrip rapi selesai.")
    if cb.get("on_finished"):
        cb["on_finished"](result)
    return result


def call_llm(system: str, user: str) -> str:
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
        "max_tokens": 8192,
        "stream": False,
    }

    last_err = None
    for attempt in (1, 2):
        try:
            with httpx.Client(timeout=600.0) as client:
                r = client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                data = r.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise ValueError("Respons LLM kosong.")
                return content.strip()
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except httpx.HTTPError as e:
            last_err = f"koneksi gagal: {e}"
        time.sleep(1.5)

    raise ConnectionError(
        f"AI tidak bisa dihubungi ({AI_MODEL} @ {AI_BASE_URL}): {last_err}. "
        "Pastikan 9router / router lokal berjalan."
    )


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


def generate_notulen_docx(output_dir: str, callbacks: dict = None) -> dict:
    """Buat notulen AI dari transkrip di output_dir → simpan DOCX + TXT preview.

    Returns {"docx_path", "txt_path", "model", "chars_in", "duration_s", "truncated"}
    """
    cb = callbacks or {}

    def log(msg):
        if cb.get("on_log"):
            cb["on_log"](msg)

    def progress(pct, msg):
        if cb.get("on_progress"):
            cb["on_progress"](pct, msg)

    try:
        start = time.time()
        log("AI notulen: membaca transkrip...")
        full_text, meta = load_transcript(output_dir)
        log(f"AI notulen: {len(full_text):,} karakter dari {meta['source_name']}.")

        progress(15, "Menyusun prompt...")
        system, user = build_prompt(full_text, meta)
        truncated = "CATATAN: transkrip asli lebih panjang" in user

        progress(25, f"Memanggil AI ({AI_MODEL})...")
        log(f"AI notulen: memanggil {AI_MODEL} @ {AI_BASE_URL} — ini bisa memakan beberapa menit.")
        notulen_md = normalize_notulen_markdown(call_llm(system, user))
        log(f"AI notulen: respons diterima ({len(notulen_md):,} karakter).")

        progress(80, "Merender DOCX...")
        out = Path(output_dir)
        stem = meta["source_name"]
        m = re.match(r"^\d{2}_(.+)$", stem)
        if m:
            stem = m.group(1)
        stem = re.sub(r"[^\w\- ]", "", stem).strip()[:50] or "notulen"

        docx_path = out / f"NotulenAI_{stem}.docx"
        MdToDocx.from_text(notulen_md, str(docx_path))
        log(f"AI notulen: DOCX -> {docx_path}")

        md_path = out / "notulen_ai.md"
        md_header = (
            f"# Notulen AI — {meta['source_name']}\n\n"
            f"- Model: `{AI_MODEL}`\n"
            f"- Transkrip: {len(full_text):,} karakter\n"
            "- Catatan: ringkasan otomatis AI; review manual disarankan.\n\n"
        )
        md_path.write_text(md_header + notulen_md.strip() + "\n", encoding="utf-8")

        pdf_path = None
        try:
            progress(90, "Merender PDF dengan Typst...")
            pdf_path = render_pdf(
                md_header + notulen_md.strip() + "\n",
                str(out / f"NotulenAI_{stem}.pdf"),
                title=f"Notulen AI — {meta['source_name']}",
            )
            log(f"AI notulen: PDF -> {pdf_path}")
        except TypstUnavailableError as exc:
            log(f"AI notulen: PDF dilewati ({exc})")

        txt_path = out / "notulen_ai.txt"
        plain = _md_to_plain(notulen_md)
        header = (
            f"NOTULEN AI — {meta['source_name']}\n"
            f"Dibuat: {datetime.now().strftime('%d %B %Y %H:%M')} | Model: {AI_MODEL}\n"
            f"Transkrip: {len(full_text):,} karakter | Ringkasan otomatis AI — review manual disarankan.\n"
            + "=" * 60 + "\n\n"
        )
        txt_path.write_text(header + plain + "\n", encoding="utf-8")

        duration_s = round(time.time() - start, 1)
        result = {
            "docx_path": str(docx_path),
            "pdf_path": pdf_path,
            "md_path": str(md_path),
            "txt_path": str(txt_path),
            "model": AI_MODEL,
            "chars_in": len(full_text),
            "duration_s": duration_s,
            "truncated": truncated,
        }
        progress(100, "Selesai.")
        log(f"AI notulen selesai dalam {duration_s}s.")
        if cb.get("on_finished"):
            cb["on_finished"](result)
        return result

    except Exception as e:  # noqa: BLE001
        if cb.get("on_error"):
            cb["on_error"](str(e))
        raise
