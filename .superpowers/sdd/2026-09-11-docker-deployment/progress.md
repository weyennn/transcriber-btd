# SDD ledger — plan: docs/superpowers/plans/2026-09-11-docker-deployment.md

## Setup notes
- Worktree: repo belum git saat plan dibuat; Task 0 melakukan `git init` + baseline commit di main branch lokal. Tidak ada main remote; branch kerja: `docker-deployment` dibuat setelah baseline (Ruling: worktree tidak praktis — repo baru init, tidak ada shared branch; risiko isolasi nol).
- Docker daemon Mac TIDAK jalan saat eksekusi dimulai → Task 7 (build/e2e) akan butuh user menyalakan Docker Desktop; task 1-6 tidak terdampak.
- `python3` system = 3.12.1, tanpa pytest → tiap implementer membuat `.venv-test` lokal (pytest+fastapi+httpx saja; engine tests yang butuh faster-whisper diverifikasi in-container Task 7).
- Plan mengandung kode lengkap untuk semua task → implementer tier murah-menengah; reviewer mid-tier; final review tier terbaik.

## Pre-flight scan (conflicts antar task & vs Global Constraints)
| Pasangan/task | Yang dicek | Temuan |
|---|---|---|
| T1 produces `HASIL_DIR,UPLOAD_DIR (Path)` ↔ T3/T4 consumes | konsisten: engine import HASIL_DIR dari paths; server import UPLOAD_DIR dari paths | ✅ cocok |
| T4 produces `ai_enabled` key ↔ T5 consumes `env.ai_enabled` | nama key identik | ✅ cocok |
| T4 `/healthz` ↔ T6 HEALTHCHECK URL | path identik `/healthz` | ✅ cocok |
| T1 test `test_default_tanpa_env` vs paths.py module-level env read | butuh importlib.reload — plan sudah memuat pola reload | ✅ |
| T2 test tmp_path save_config vs `_CONFIG_DIR.mkdir` di save_config | save_config existing sudah mkdir(parents=True) | ✅ |
| T3 hapus PROJECT_ROOT dari engine.py | plan mewajibkan grep PROJECT_ROOT di engine dulu; engine.py memang hanya pakai utk HASIL_DIR | ✅ (diverifikasi controller: baris 27-28 hanya definisi) |
| T4 notulen_ai guard posisi | guard SEBELUM baca body — sesuai spec D-5 (503) | ✅ |
| T6 .dockerignore exclude `docs/` vs spec §5.3 | spec tidak exclude docs/; plan menambah — Ruling: dipertahankan (docs tidak dibutuhkan runtime; image lebih kecil; tidak ada konflik dgn spec yg hanya menyebut gui/services) | Ruling tercatat |
| Global: "engine.py tidak disentuh (D-9 WDAC)" vs T3 modify engine.py | T3 hanya mengubah sumber HASIL_DIR, tidak menyentuh apply_wdac_patch/load_model — konsisten dgn spec §4 yg secara eksplisit menyebut penyatuan HASIL_DIR ke paths.py | ✅ spec mengizinkan |

Scan selesai: tidak ada konflik blocker. 1 ruling (.dockerignore docs/) tercatat di atas.

## Rulings
- Ruling: worktree dilewati, kerja di branch `docker-deployment` pada repo lokal baru — tidak ada main bersama/remote, user eksplisit meminta eksekusi di folder ini. Biaya jika salah: history lokal berantakan; recoverable via git reset.
- Ruling: `.dockerignore` menambah `docs/` di luar teks spec §5.3 — image lebih kecil, docs tak dipakai runtime. Biaya jika salah: rebuild menambah docs kembali (trivial).

## Progress
(belum ada task selesai)
