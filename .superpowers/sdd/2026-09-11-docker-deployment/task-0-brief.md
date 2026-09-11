### Task 0: Git init + baseline commit

Repo belum version-controlled; semua task berikut butuh commit granularity.

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Buat .gitignore**

```
.venv/
.venv-mac/
.pytest_cache/
__pycache__/
*.pyc
.DS_Store
uploads/
transcribe_hasil/
data/
*.egg-info/
```

- [ ] **Step 2: Init + baseline commit**

```bash
cd /Users/wayeien/Documents/firmware_transcribe
git init
git add -A
git commit -m "chore: baseline sebelum dockerization"
```

---