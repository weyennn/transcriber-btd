"""Pemanggil model bahasa untuk penyusunan naskah.

Memakai pemanggil dan konfigurasi yang sudah ada di aplikasi
(src.notulen.ai_generator), sehingga modul dokumen tidak memerlukan titik akhir
baru dan tidak menyimpan salinan konfigurasi sendiri:

    TRANSCRIBE_AI_BASE_URL   titik akhir yang sesuai antarmuka OpenAI
    TRANSCRIBE_AI_MODEL      nama model
    TRANSCRIBE_AI_API_KEY    kunci bila diperlukan

Berkas ini sengaja dipisahkan dari penyusun naskah supaya penyusun dapat diuji
tanpa jaringan.
"""

from __future__ import annotations


def konfigurasi() -> dict:
    """Konfigurasi yang sedang dipakai, tanpa menampilkan nilai kunci."""
    from src.notulen.ai_generator import ai_config
    return ai_config()


def panggil(system: str, user: str, cancel_event=None) -> str:
    """Panggil model dan kembalikan isi jawabannya.

    Pemanggil aplikasi diimpor di dalam fungsi, sehingga pemeriksa dan penyusun
    naskah dapat dipakai di lingkungan tanpa pustaka jaringan.
    """
    from src.notulen.ai_generator import call_llm
    return call_llm(system, user, cancel_event=cancel_event)
