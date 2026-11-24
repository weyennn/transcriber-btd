"""Catatan kaki yang menandai keluaran buatan AI (satu sumber teks untuk semua format)."""

CATATAN_AI = (
    "Catatan: isi dokumen ini dihasilkan dengan bantuan kecerdasan buatan (AI) dari transkrip "
    "rekaman. Hasilnya perlu ditinjau dan dicocokkan dengan rekaman sebelum digunakan sebagai rujukan resmi."
)

CATATAN_TRANSKRIP = (
    "Catatan: transkrip ini dihasilkan otomatis oleh model kecerdasan buatan (AI) pengenal suara "
    "dan dapat memuat kesalahan penulisan nama, istilah, atau angka."
)

NAMA_BAHASA = {"en": "Inggris", "id": "Indonesia", "ms": "Melayu", "ar": "Arab", "zh": "Mandarin",
               "ja": "Jepang", "ko": "Korea", "fr": "Prancis", "de": "Jerman", "es": "Spanyol",
               "nl": "Belanda", "ru": "Rusia", "hi": "Hindi", "jw": "Jawa", "su": "Sunda"}


def aturan_terjemahan(bahasa) -> str:
    """Instruksi terjemahan bila rekaman bukan berbahasa Indonesia; kosong bila Indonesia/tidak diketahui."""
    kode = str(bahasa or "").strip().lower()
    if not kode or kode in {"id", "auto"}:
        return ""
    nama = NAMA_BAHASA.get(kode, f"kode '{kode}'")
    return (
        f"Transkrip ini berbahasa {nama}. Tulis hasilnya dalam Bahasa Indonesia baku yang wajar dan mengalir, "
        "seperti ditulis penutur asli: terjemahkan makna dan maksud kalimat, jangan kata per kata, dan jangan "
        "meniru susunan kalimat bahasa sumber. Pakai satu padanan yang konsisten untuk istilah yang sama. "
        "Biarkan nama orang, lembaga, produk, singkatan, dan istilah teknis yang lazim tetap dalam bentuk aslinya "
        "(boleh diberi padanan Indonesia dalam kurung pada penyebutan pertama). Angka, tanggal, dan nama tidak boleh berubah."
    )
