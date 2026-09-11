### Task 5: Frontend — disable tombol AI saat flag off

**Files:**
- Modify: `src/web/static/app.js:40-43` (blok `ai` di `checkEnv`)

**Interfaces:**
- Consumes: `env.ai_enabled: bool` dari `/api/env` (Task 4)
- Produces: tidak ada interface baru untuk task lain.

- [ ] **Step 1: Patch `app.js`**

Ganti blok `ai` di `checkEnv()` (baris 40-43) menjadi:

```javascript
    const ai = env.ai_enabled
      ? `<span class="ok">AI ${env.ai.model}</span>`
      : `<span class="warn">AI notulen nonaktif</span>`;
    $("env-status").innerHTML = `${ff} · ${model} · ${ai}`;

    // Feature flag AI (D-5): disable tombol + tooltip saat off
    if (!env.ai_enabled) {
      btnAINotulen.disabled = true;
      btnAINotulen.title = "Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)";
      btnAINotulen.style.opacity = "0.5";
      btnAINotulen.style.cursor = "not-allowed";
    }
```

- [ ] **Step 2: Verifikasi manual lokal**

Jalankan server lokal (venv-mac/python3 dengan deps) dengan `AI_ENABLED=false`, buka dashboard: badge menampilkan "AI notulen nonaktif", tombol 🤖 disabled + tooltip. Ulangi dengan `AI_ENABLED=true`: badge normal, tombol aktif.
Jika deps lokal belum siap, verifikasi ditunda ke Task 7 e2e (catat di commit message).

- [ ] **Step 3: Commit**

```bash
git add src/web/static/app.js
git commit -m "feat: UI disable tombol AI notulen saat AI_ENABLED=false"
```

---