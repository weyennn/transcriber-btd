# Audit Anti-Slop UI 001, Follow-up

Tanggal follow-up: 2026-09-17
Mode: AFTER
Scope: seluruh temuan 1 sampai 12 dari `anti-slop/audit-001-2026-09-17.md`.

## Status

Semua temuan yang disetujui telah diperbaiki di:

- `src/web/templates/index.html`
- `src/web/static/app.js`
- `src/web/static/style.css`
- `DESIGN.md`

## Resolved findings

1. **Resolved**: `setFile()` sekarang menetapkan `selectedFile`, mereset path upload lama, menolak file invalid, dan mengaktifkan tombol transkripsi untuk file audio valid.
2. **Resolved**: item riwayat sekarang memakai tombol native `.history-open`, sehingga dapat dioperasikan keyboard.
3. **Resolved**: riwayat memiliki loading, empty, dan error state; error menyediakan tombol `Muat ulang riwayat` yang memanggil refresh nyata.
4. **Resolved**: overlay pembuka mengunci shell dengan `inert`, menangani Tab dan Escape, lalu memindahkan fokus ke `workspace-heading` atau login setelah ditutup.
5. **Resolved**: `DESIGN.md` mendokumentasikan identity, visual language, dials, motif, dan alasan keputusan. UI tetap memakai bahasa Indonesia yang terbaca, tanpa menampilkan klaim draft kepada pengguna karena arah visual sekarang telah didokumentasikan.
6. **Resolved**: portal disederhanakan menjadi satu ring dan satu glow, dekorasi bertumpuk dikurangi, serta motion dibatasi pada transisi masuk dan keluar yang punya fungsi.
7. **Resolved**: copy status hero diubah menjadi `SUMBER AUDIO`, badge live disembunyikan, ring pulse dihapus, dan status environment memakai teks serta class state nyata.
8. **Resolved**: pasangan warna utama dihitung: ink/cream 12.32:1, muted/cream 5.82:1, maroon/white 12.35:1, warning/cream 8.70:1. Focus ring memakai maroon dengan white separation.
9. **Resolved**: panah dekoratif di alur hero dihapus; teks menjelaskan hubungan audio dan teks secara langsung.
10. **Resolved**: visual hero tidak lagi dihapus pada mobile. Ia diturunkan menjadi blok yang tetap terlihat dan diberi ringkasan teks.
11. **Resolved**: tabs memakai `tabindex` roving, `aria-selected`, `aria-controls`, `aria-labelledby`, serta ArrowLeft, ArrowRight, Home, dan End.
12. **Resolved**: status environment dan state riwayat tidak lagi memakai `innerHTML`; node dinamis dibuat dengan DOM API dan `textContent`. Placeholder download `href="#"` dihapus.

## Verification evidence

- `node --check src/web/static/app.js`: PASS.
- HTML div/section balance dan CSS brace balance: PASS.
- Source assertions untuk `selectedFile`, native history controls, no `innerHTML`, dan satu AI control: PASS.
- `tests/test_auth.py`: 6 passed.
- `tests/test_history_delete.py` dan `tests/test_ai_flag.py`: tidak dapat dijalankan penuh pada system Python karena dependency runtime `faster_whisper` tidak terpasang; focused auth suite tetap PASS.
- Browser audit server memakai stub `faster_whisper` in-memory, tanpa instalasi atau perubahan dependency.
- Browser desktop: page loaded, portal focus awal berada di `portal-enter`, portal close memindahkan fokus ke `workspace-heading`, console errors kosong, horizontal overflow false.
- Browser file flow: file `audit.mp3` valid muncul di file info dan `Mulai transkripsi` menjadi enabled.
- Browser tabs: ArrowRight memindahkan fokus ke `tab-json` dan mengubah `aria-selected` menjadi `true`.
- Browser mobile viewport 390x844: horizontal overflow false, workspace layout `flex` dan tersusun vertikal, hero art tetap terlihat sebagai `grid`, console errors kosong.
- Audit server dan browser tab telah ditutup setelah verifikasi.

## Remaining limitation

Transkripsi engine nyata tidak dijalankan dalam browser follow-up karena environment macOS aktif tidak memiliki extension `faster_whisper` yang dapat diimpor, sedangkan `.venv` berisi executable Windows yang tidak dapat dijalankan di macOS. Perubahan flow upload dan client state sudah diuji dengan file audio sintetis di browser; transkripsi end-to-end tetap memerlukan runtime target yang sesuai.
