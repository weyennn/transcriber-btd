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
Task 0: complete (commit 2b85675 baseline di main + branch docker-deployment dibuat)
Task 1: complete (commit 7da4967, review clean — Spec ✅, task quality Approved; tidak ada Critical/Important/Minor; strengths: .strip() whitespace handling, nilai persis sesuai constraint, fungsi existing tak tersentuh; verdict lengkap reviewer terpotong di transport log, isi terverifikasi dari transcript 14:59:36-37)
Task 2: complete (commit 430b2bb, review clean — Spec ✅; patch verbatim brief, prioritas CONFIG_DIR benar, signature tak berubah)
Task 3: complete (commit 22c40e9, review clean — Spec ✅; engine import HASIL_DIR dari paths, PROJECT_ROOT dihapus setelah grep membuktikan tak dipakai; failure test_wdac_patch pre-existing environment, bukan regresi — verifikasi final in-container Task 7)
Catatan transport: verdict reviewer 2x terpotong di log transport (bukan hilang — isi terverifikasi dari blok assistant di transcript). Dampak: tidak ada; kalau ada Minor tersembunyi akan tertangkap final review.
Task 4: implementasi selesai (commit 2e9c7f1, 3/3 test + regresi 6/6 PASS) — menunggu task review.
Ruling (Task 4 follow-up): bootstrap re-exec di docx_converter.py:64 akan DIPATCH dengan guard (skip saat `os.environ.get("DATA_DIR")` ter-set, yaitu di container) — bukan dihapus, agar perilaku Windows dev (R-13) utuh. Tanpa guard, container hang/re-exec saat AI_ENABLED=true dipakai nanti. Biaya jika salah: satu kondisi kecil di fungsi bootstrap; reversible. Dijadwalkan sebagai bagian Task 6.
Ruling (test_web.py 2 failing): BUKAN regresi — test lama expect endpoint /api/notulen/ai 200, padahal AI_ENABLED default false (spec D-5). Perilaku baru BENAR. Update test_web.py ditunda ke Task 7 (set-env AI_ENABLED=true di fixture test tersebut, atau pisahkan). Biaya jika salah: 2 test merah di suite lokal sampai diperbaiki; tidak memengaruhi container (test in-container Task 7 memakai subset yang tidak mencakup 2 test itu — sesuai brief Task 7 Step 2).
Ruling (concern .dockerignore src/services/): TERVERIFIKASI AMAN — `grep -rn "src.services" src/web src/core src/notulen src/export src/utils` = 0 hasil; tidak ada import runtime ke src.services. Exclude tetap.
Ruling (Task 5 review ⚠️ — REAL, masuk fix loop): reviewer menemukan `endJob()` (app.js:195) dan catch handler notulen (app.js:318) meng-set `btnAINotulen.disabled = false` tanpa cek flag → tombol AI re-enable setelah job pertama meski AI_ENABLED=false. Kode 195/318 adalah kode LAMA, tapi dengan adanya flag baru, perilakunya sekarang SALAH. Fix: simpan status flag di variabel module-level `aiEnabled` (diisi di checkEnv dari env.ai_enabled), lalu kedua lokasi itu meng-set `btnAINotulen.disabled = !aiEnabled`. Ini penyesuaian kecil melampaui snippet verbatim brief — dibenarkan karena brief tidak mengetahui interaksi dengan kode lama. Biaya jika salah: tombol AI tetap aktif di UI tapi API tetap menolak 503 (pertahanan berlapis), jadi dampak salah hanya UX.
Task 4: complete (commit 2e9c7f1, review clean — Spec ✅; UPLOAD_DIR dari paths, AI_ENABLED, ai_enabled di /api/env, guard 503, /healthz)
Task 5: complete (commit b520ac7 + fix 21135db; fix round 1/5: 2 finding ADDRESSED, 0 open — re-review clean)
Task 6: complete (commit 2a54801, review clean statis; build/e2e ditunda ke Task 7 karena Docker daemon mati)
Guard docx: complete (commit e8bd23b + tests/test_docx_bootstrap_guard.py 2 passed)
Final review: MERGE-READY BERSYARAT — 0 Critical · 3 Important · 6 Minor. Semua Important bermuara ke Task 7 runtime. Report lengkap: final-review.md.
Task 7: DIHENTIKAN atas instruksi user — build & e2e TIDAK BOLEH dijalankan di Mac ini (docker daemon di sini memang flaky/putus). Verifikasi build + e2e dipindah ke btd-server (atau mesin lain yang user tentukan). Belum ada artefak Docker yang dibuat di Mac (0 image, 0 container, 0 folder data/).
Sisa pekerjaan Task 7 yang TIDAK butuh Docker (bisa dikerjakan kapan saja): fix tests/test_web.py (2 test AI perlu AI_ENABLED=true) + tulis DEPLOY.md. Menunggu keputusan user.
