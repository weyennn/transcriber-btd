"""Identitas pencatat dari sesi login (tanpa dependensi berat)."""


def nama_pencatat(user: dict) -> str:
    """Nama pencatat dari akun Google yang login; kosong untuk mode dev/lokal."""
    if user.get("dev"):
        return ""
    nama = str(user.get("name", "")).strip()
    if nama:
        return nama
    email = str(user.get("email", "")).strip()
    return email.split("@", 1)[0] if email else ""
