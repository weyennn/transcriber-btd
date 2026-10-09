"""Pekerjaan penyusunan dokumen resmi dari folder hasil transkripsi.

Alur: baca transkrip → susun naskah per bagian → periksa cakupan sumber, bentuk
penyajian, dan keterlacakan → tulis Markdown, PDF, dan DOCX. Bila salah satu
pemeriksaan menolak, pekerjaan berakhir dengan galat yang menyebut temuannya dan
tidak ada dokumen yang ditulis.

Callback contract sama dengan jalur notulen (dipanggil dari thread worker):
    on_log(message)
    on_progress(percent, message)
    on_finished(result: dict)
    on_error(error)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from src.core.engine import CancelledError
from src.notulen import ai_generator
from src.pandora_documents import checks, composer, render
from src.pandora_quality.slop_gate import laporan

PANJANG_ISIAN = 200
NAMA_MD = "dokumen_{jenis}.md"


class DokumenDitolak(ValueError):
    """Naskah tidak lolos pemeriksaan, sehingga dokumen tidak ditulis."""


def daftar_jenis() -> list[dict]:
    """Jenis dokumen dan isian kepalanya, untuk dibaca antarmuka."""
    return [
        {"jenis": jenis, "nama": rencana["nama"],
         "kepala": [{"kunci": kunci, "label": label} for kunci, label in rencana["kepala"]]}
        for jenis, rencana in composer.RENCANA.items()
    ]


def nama_berkas(jenis: str, nama_folder: str) -> dict:
    """Nama berkas keluaran untuk satu jenis dokumen pada satu folder hasil."""
    stem = nama_folder
    cocok = re.match(r"^\d{2,}_(.+)$", stem)
    if cocok:
        stem = cocok.group(1)
    stem = re.sub(r"[^\w\- ]", "", stem).strip()[:50] or "dokumen"
    awalan = composer.RENCANA[jenis]["nama"].replace(" ", "")
    return {
        "md": NAMA_MD.format(jenis=jenis),
        "pdf": f"{awalan}_{stem}.pdf",
        "docx": f"{awalan}_{stem}.docx",
        "jejak": f"dokumen_{jenis}.jejak.json",
    }


def bersihkan_isian(nilai) -> str:
    """Rapikan satu isian pengguna: satu baris, tanpa karakter kendali."""
    teks = re.sub(r"[\x00-\x1f\x7f]+", " ", str(nilai or ""))
    return re.sub(r"\s+", " ", teks).strip()[:PANJANG_ISIAN]


def _arsipkan(berkas: Path) -> None:
    """Beri nomor urut pada berkas lama supaya penyusunan ulang tidak menimpanya."""
    if not berkas.exists():
        return
    for urutan in range(1, 1000):
        calon = berkas.with_name(f"{berkas.stem}-{urutan}{berkas.suffix}")
        if not calon.exists():
            berkas.rename(calon)
            return


def susun_dokumen(output_dir: str, jenis: str = "laporan_kegiatan", judul: str = "",
                  kepala: dict | None = None, callbacks: dict | None = None,
                  cancel_event=None) -> dict:
    """Susun dokumen resmi dari transkrip di output_dir.

    Returns {"md_path", "pdf_path", "docx_path", "jenis", "model", "chars_in",
    "duration_s", "cara"}. pdf_path bernilai None bila perkakas typst tidak ada.
    """
    cb = callbacks or {}
    cancel_event = cancel_event or cb.get("cancel_event")

    def log(msg):
        if cb.get("on_log"):
            cb["on_log"](msg)

    def progress(pct, msg):
        if cb.get("on_progress"):
            cb["on_progress"](pct, msg)

    def periksa_batal():
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

    def panggil(system, user):
        periksa_batal()
        if cancel_event is None:
            return ai_generator.call_llm(system, user)
        return ai_generator.call_llm(system, user, cancel_event=cancel_event)

    try:
        if jenis not in composer.RENCANA:
            raise ValueError(f"Jenis dokumen tidak dikenal: {jenis}")
        mulai = time.time()
        periksa_batal()
        out = Path(output_dir)
        rencana = composer.RENCANA[jenis]
        log(f"Dokumen: membaca transkrip untuk {rencana['nama']}...")
        full_text, meta = ai_generator.load_transcript(output_dir)
        judul = bersihkan_isian(judul) or re.sub(r"^\d{2,}_", "", out.name).replace("_", " ")
        isian = {kunci: bersihkan_isian((kepala or {}).get(kunci)) for kunci, _ in rencana["kepala"]}
        log(f"Dokumen: {len(full_text):,} karakter transkrip, {len(rencana['bagian'])} bagian.")

        def saat_bagian(urutan, jumlah, nama_bagian):
            progress(10 + int(65 * (urutan - 1) / jumlah),
                     f"Menyusun bagian {urutan} dari {jumlah}: {nama_bagian}...")

        naskah = composer.rakit(full_text, judul, jenis, panggil,
                                periksa=checks.periksa_bentuk, saat_bagian=saat_bagian)
        periksa_batal()
        log(f"Dokumen: naskah tersusun ({naskah.jejak['cara']}, {naskah.jejak['detik']} detik).")

        progress(78, "Memeriksa cakupan sumber dan bentuk naskah...")
        markdown = naskah.ke_markdown(isian)
        pelanggaran = checks.periksa_cakupan(naskah.jejak)
        pelanggaran += checks.periksa_keterlacakan(
            markdown, {"source_name": meta["source_name"], "output_dir": str(out)})
        temuan = checks.periksa_bentuk(markdown)
        if pelanggaran or temuan:
            rincian = [*pelanggaran]
            if temuan:
                rincian.append(laporan(temuan, rencana["nama"]))
            raise DokumenDitolak(
                "Dokumen tidak dinyatakan selesai karena naskah ditolak pemeriksa.\n"
                + "\n".join(rincian)
            )
        log("Dokumen: cakupan sumber utuh, naskah lolos gerbang penyajian.")

        nama = nama_berkas(jenis, out.name)
        for kunci in ("md", "pdf", "docx", "jejak"):
            _arsipkan(out / nama[kunci])

        md_path = out / nama["md"]
        md_path.write_text(markdown, encoding="utf-8")

        # Kegagalan satu pembentuk berkas tidak membatalkan berkas lain.
        progress(84, "Membentuk DOCX...")
        docx_path = None
        try:
            docx_path = render.bentuk_docx(naskah, out / nama["docx"], isian)
            log(f"Dokumen: DOCX -> {docx_path}")
        except Exception as exc:  # noqa: BLE001
            log(f"Dokumen: DOCX gagal, berkas lain tetap tersedia ({exc})")

        progress(92, "Membentuk PDF...")
        pdf_path = None
        try:
            pdf_path = render.bentuk_pdf(naskah, out / nama["pdf"], isian)
            log(f"Dokumen: PDF -> {pdf_path}")
        except render.PerkakasTidakTersedia as exc:
            log(f"Dokumen: PDF dilewati ({exc})")
        except Exception as exc:  # noqa: BLE001
            log(f"Dokumen: PDF gagal, berkas lain tetap tersedia ({exc})")

        duration_s = round(time.time() - mulai, 1)
        # Jejak adalah berkas kerja: sumber, sidik isi transkrip, dan cakupan
        # hidup di sini, bukan di dokumen yang dibagikan.
        jejak = {
            **naskah.jejak,
            "jenis": jenis,
            "judul": judul,
            "kepala": isian,
            "folder": out.name,
            "model": ai_generator.AI_MODEL,
            "sha256_transkrip": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            "durasi_audio_s": meta.get("audio_duration"),
        }
        (out / nama["jejak"]).write_text(
            json.dumps(jejak, ensure_ascii=False, indent=2), encoding="utf-8")

        result = {
            "jenis": jenis,
            "md_path": str(md_path),
            "pdf_path": pdf_path,
            "docx_path": docx_path,
            "model": ai_generator.AI_MODEL,
            "chars_in": len(full_text),
            "cara": naskah.jejak["cara"],
            "duration_s": duration_s,
        }
        progress(100, "Dokumen resmi selesai.")
        log(f"Dokumen selesai dalam {duration_s}s.")
        if cb.get("on_finished"):
            cb["on_finished"](result)
        return result

    except CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        if cb.get("on_error"):
            cb["on_error"](str(e))
        raise
