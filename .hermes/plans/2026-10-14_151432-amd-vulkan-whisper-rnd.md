# AMD Vulkan Whisper R&D Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Determine, with an isolated and reversible benchmark, whether the BTD server’s AMD Radeon RX 570 can transcribe Indonesian audio via `whisper.cpp` + Vulkan faster and reliably enough to justify a future optional backend for Mesin Transcriber.

**Architecture:** Keep production `mesin-transcribe` untouched: it remains `faster-whisper` + CPU `int8`, keeps its current SQLite/data mounts, and continues serving `http://10.14.7.237:8765/transcribe/`. Build a separate one-shot benchmark image/service that receives a single sanitized fixture read-only, exposes no port, uses no production data volumes, and receives only `/dev/dri` plus the render-group GID needed by Vulkan. Its result is a small JSON/CSV metrics artifact outside production data. Only after GPU viability is proven should an adapter interface be designed; no production engine switch is part of this R&D.

**Tech Stack:** Linux Mint 22.3 host; AMD Radeon RX 570/Polaris (`amdgpu`); Mesa RADV Vulkan; Docker Compose; `whisper.cpp` Vulkan backend; current app Python/FastAPI job queue; pytest.

---

## Verified starting context

- Production container: `mesin-transcribe`, healthy, no restarts, route returns HTTP 200.
- Current production backend: `faster-whisper 1.2.1` / `CTranslate2 4.8.2`, explicit `device="cpu"`, `compute_type="int8"`.
- Host GPU: AMD Radeon RX 570 (Polaris/Ellesmere), kernel driver `amdgpu` active.
- Host exposes `/dev/dri/renderD128`, owned `root:render`, mode `660`; user `magangbtd` is not in `render`.
- AMD Vulkan ICD is installed at `/usr/share/vulkan/icd.d/radeon_icd.json`, but the current user cannot open the render node. No ROCm or OpenCL toolchain has been established.
- Production compose mounts `./data/{models,uploads,hasil,config}`, runs app as host UID/GID, and limits it to 4 GiB. Do not change these in R&D.
- Local checkout: `/Users/wayeien/Documents/firmware_transcribe`, commit `d632b90`. Existing untracked `.release-stage/`, `.server-update-20261009/`, and archive artifacts are out of scope and must remain untouched.

## Non-goals and guardrails

- Do not edit/rebuild/recreate `mesin-transcribe` or `mesin-transcribe-proxy`.
- Do not modify production Compose, Nginx, `.env`, application SQLite, user uploads, models cache, or results.
- Do not add `magangbtd` permanently to the host `render` group in the R&D phase.
- Do not expose benchmark ports or bind benchmark artifacts inside `data/`.
- Do not evaluate transcript content from a real user upload. Use only the existing project fixture (`sample_audio/sample_75s.mp3`) or a newly approved non-sensitive fixture.
- Never treat a successful Vulkan initialization as a performance win. Compare elapsed time, RTF, output availability, and transcript agreement with CPU.

## Decision gates

| Gate | Pass criterion | Result if failed |
|---|---|---|
| G1: host access | Vulkan sees RX 570 from a temporary privileged diagnostic context | Stop; capture driver/permission evidence. Do not alter production. |
| G2: container access | Isolated container sees exactly the AMD Vulkan device and can enumerate it | Stop; remove temporary service/image only after approval. |
| G3: functional transcription | Vulkan `whisper.cpp` produces a non-empty transcript from the benchmark fixture | Record failure; retain CPU production. |
| G4: comparative quality | GPU transcript meets agreed tolerance vs CPU baseline (default: non-empty, language detected/forced `id`, no crash, and manually reviewed sample is materially equivalent) | Do not propose backend adoption. |
| G5: performance | GPU wall time and real-time factor are better than CPU baseline by a pre-agreed meaningful margin (recommended >=20% on 75 s sample), with no host instability | Proceed to optional-backend design only. |

**Important capacity caveat:** RX 570 VRAM varies by board (commonly 4 or 8 GiB). Record actual VRAM before selecting models. The first benchmark should use `small` with Indonesian forced; benchmark `medium` only if VRAM/use is stable. Do not claim it can run medium before measurement.

---

### Task 1: Freeze a reproducible CPU baseline

**Objective:** Produce a repeatable CPU result for exactly one non-sensitive fixture before GPU experimentation.

**Files:**
- Create: `benchmarks/README.md`
- Create: `benchmarks/fixtures/README.md`
- Create: `benchmarks/results/.gitkeep`
- Create: `benchmarks/run_cpu_baseline.sh`
- Create: `benchmarks/parse_result.py`
- Test: `tests/test_benchmark_result_parser.py`

**Step 1: Define the fixture policy**

Create `benchmarks/fixtures/README.md` specifying:

```markdown
Only synthetic or explicitly approved non-sensitive audio may be benchmarked.
Default fixture: ../../sample_audio/sample_75s.mp3 (read-only).
Never copy a production user upload or a file under data/uploads into benchmarks.
```

**Step 2: Write failing parser tests**

Create `tests/test_benchmark_result_parser.py` with fixed representative `whisper.cpp` output lines. Assert parser output includes non-negative `wall_seconds`, non-empty `backend`, `model`, and `fixture_sha256`, and returns `None` for an absent timing line instead of inventing a value.

**Step 3: Run the focused test and confirm failure**

Run:

```bash
pytest -q tests/test_benchmark_result_parser.py
```

Expected: FAIL because `benchmarks.parse_result` does not exist.

**Step 4: Implement deterministic metrics parsing**

Create `benchmarks/parse_result.py`. It must parse only explicit tool output, calculate RTF as `wall_seconds / audio_seconds` only if both values are numeric and positive, and emit JSON with this exact shape:

```json
{
  "schema_version": 1,
  "backend": "cpu-faster-whisper",
  "model": "small",
  "language": "id",
  "fixture_path": "sample_audio/sample_75s.mp3",
  "fixture_sha256": "...",
  "audio_seconds": 75.0,
  "wall_seconds": 0.0,
  "rtf": 0.0,
  "exit_code": 0,
  "transcript_sha256": "...",
  "created_at_utc": "..."
}
```

Do not store source audio, raw user data, API keys, or production filesystem paths in results.

**Step 5: Implement CPU baseline script**

`benchmarks/run_cpu_baseline.sh` must:

1. Refuse any fixture outside repository `sample_audio/` unless `BENCHMARK_FIXTURE_APPROVED=1` is explicitly set.
2. Write output only to `benchmarks/results/`.
3. Invoke a pinned local/throwaway CPU runner (not production container and not production `data/models`).
4. Record wall clock with a monotonic timer and the fixture/transcript SHA-256.
5. Produce a JSON metrics file plus an isolated transcript text file.
6. Exit non-zero when transcription fails or transcript is empty.

**Step 6: Verify baseline**

Run focused parser tests, then execute the script once using `sample_audio/sample_75s.mp3`. Confirm:

```bash
pytest -q tests/test_benchmark_result_parser.py
python3 -m json.tool benchmarks/results/cpu-*.json
```

Expected: tests pass; JSON has explicit timings and hashes; no `data/` path changes.

**Step 7: Commit**

```bash
git add benchmarks tests/test_benchmark_result_parser.py
git commit -m "test: add isolated transcription benchmark baseline"
```

---

### Task 2: Prove host Vulkan readiness without production changes

**Objective:** Establish whether the RX 570 can be enumerated by Vulkan, and whether the only blocker is render-node permission.

**Files:**
- Create: `docs/rnd/amd-vulkan-host-preflight.md`
- Create: `scripts/check_amd_vulkan_host.sh`
- Test: none (host diagnostic script with documented expected signals)

**Step 1: Write a read-only preflight script**

Create `scripts/check_amd_vulkan_host.sh`, which prints only:

- PCI device ID/model and bound kernel driver,
- `/dev/dri/renderD*` ownership/mode,
- current user/group IDs,
- installed Radeon Vulkan ICD filenames,
- `vulkaninfo --summary` result (when available),
- GPU name, driver version, and VRAM when the Vulkan probe permits it.

It must not call `usermod`, `groupadd`, package managers, Docker lifecycle commands, or write outside `/tmp`.

**Step 2: Execute in two read-only contexts**

On the host, run once as the deployment user (expected current permission failure), and once through an explicitly authorized non-interactive group context or a temporary diagnostic container with `/dev/dri` plus `group_add` equal to the host render GID. Avoid a permanent host group change.

**Step 3: Document G1 result**

Record sanitized evidence in `docs/rnd/amd-vulkan-host-preflight.md`:

- host kernel/mesa versions,
- GPU PCI ID and VRAM,
- user/group issue observed,
- whether Vulkan reports a physical device.

No full logs, tokens, user files, or unrelated host state.

**Step 4: Commit**

```bash
git add scripts/check_amd_vulkan_host.sh docs/rnd/amd-vulkan-host-preflight.md
git commit -m "docs: record AMD Vulkan preflight procedure"
```

---

### Task 3: Create an isolated `whisper.cpp` Vulkan benchmark image

**Objective:** Build a dedicated GPU benchmark image that is unable to affect production transcriber state.

**Files:**
- Create: `benchmarks/Dockerfile.whisper-vulkan`
- Create: `benchmarks/docker-compose.vulkan-benchmark.yml`
- Create: `benchmarks/run_vulkan_benchmark.sh`
- Create: `benchmarks/verify_isolation.sh`
- Modify: `.dockerignore` only if needed to keep context small; do not weaken secret/data exclusions.
- Test: `tests/test_benchmark_compose.py`

**Step 1: Write failing Compose-isolation tests**

Create `tests/test_benchmark_compose.py` asserting the benchmark Compose file:

- declares no `ports`, `container_name`, `restart`, or production `depends_on`;
- mounts fixture read-only;
- mounts only `benchmarks/results` writable;
- never mounts `./data`, `.env`, source production uploads, configs, or SQLite;
- passes `/dev/dri` and sets `group_add` via `${RENDER_GID:?RENDER_GID is required}`;
- sets the AMD ICD explicitly using `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json` only after confirming that exact in-image path.

**Step 2: Run the test to confirm failure**

```bash
pytest -q tests/test_benchmark_compose.py
```

Expected: FAIL because the Compose benchmark definition does not exist.

**Step 3: Build Dockerfile with Vulkan backend enabled**

`benchmarks/Dockerfile.whisper-vulkan` must use a pinned, reviewed upstream `whisper.cpp` source revision/image digest. Build `whisper-cli` with Vulkan enabled (`GGML_VULKAN=1`) and include only required runtime libraries, including Mesa RADV Vulkan userspace. Record upstream revision and image digest in comments or build labels.

Do not use `--privileged`, host networking, Docker socket mounts, or writable root filesystem unnecessarily. The executable must be invoked as non-root and must accept an input audio path/model path/output path from arguments.

**Step 4: Add Compose service**

Create `benchmarks/docker-compose.vulkan-benchmark.yml`:

```yaml
services:
  whisper-vulkan-benchmark:
    build:
      context: ..
      dockerfile: benchmarks/Dockerfile.whisper-vulkan
    user: "${BENCHMARK_UID:?}:${BENCHMARK_GID:?}"
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "${RENDER_GID:?RENDER_GID is required}"
    environment:
      VK_ICD_FILENAMES: /usr/share/vulkan/icd.d/radeon_icd.json
    volumes:
      - ../sample_audio:/fixtures:ro
      - ../benchmarks/results:/results
    read_only: true
    tmpfs:
      - /tmp:size=256m
```

Treat this as structural intent: validate the exact `whisper.cpp` model/cache path and any narrowly scoped model volume separately. Do not pull models into production cache. If a cache is required, use `benchmarks/model-cache/` and ensure it is ignored.

**Step 5: Add a hard isolation verifier**

`benchmarks/verify_isolation.sh` must run `docker compose config`, inspect the resulting service definition, and fail if a disallowed mount, port, privileged mode, Docker socket, or production service reference exists.

**Step 6: Validate without running GPU inference**

Run:

```bash
pytest -q tests/test_benchmark_compose.py
docker compose -f benchmarks/docker-compose.vulkan-benchmark.yml config
./benchmarks/verify_isolation.sh
```

Expected: all pass. Do not run the service until G1 passes and an explicit R&D execution approval is given.

**Step 7: Commit**

```bash
git add benchmarks .dockerignore tests/test_benchmark_compose.py
git commit -m "feat: add isolated Vulkan whisper benchmark image"
```

---

### Task 4: Run a bounded Vulkan functional benchmark

**Objective:** Prove G2 and G3 using a one-shot container and one 75-second non-sensitive fixture.

**Files:**
- Modify: `benchmarks/run_vulkan_benchmark.sh`
- Create: `docs/rnd/amd-vulkan-benchmark-YYYY-MM-DD.md` (actual run record)
- Create: `benchmarks/results/vulkan-*.json` (ignored runtime artifact)

**Step 1: Preflight the exact GPU run context**

Before build/run, record:

```bash
getent group render
stat -c '%n owner=%U group=%G mode=%a' /dev/dri/renderD128
docker compose -f benchmarks/docker-compose.vulkan-benchmark.yml config
```

Set `BENCHMARK_UID`, `BENCHMARK_GID`, and `RENDER_GID` from actual numeric values. Never infer the group ID from another machine.

**Step 2: Build separately**

Build only the isolated service. Inspect the image’s executable and Vulkan ICD path before inference. If build fails, stop and document it; do not install host packages or touch production service.

**Step 3: Confirm GPU enumeration inside container**

Run a one-shot `vulkaninfo --summary` in the benchmark service context. Pass G2 only if output names the AMD physical device and does not fall back to lavapipe/software rendering.

**Step 4: Execute one bounded transcription**

Run `whisper-cli` with:

- model: `small` quantized model appropriate for `whisper.cpp`;
- language: Indonesian (`id`);
- no translation;
- fixture: `/fixtures/sample_75s.mp3`;
- output: `/results/vulkan-<timestamp>.txt`;
- a command timeout (e.g. 10 minutes);
- explicit verbose timing output.

Do not run concurrent jobs and do not test `medium` yet.

**Step 5: Capture structured result**

Parse timing to `benchmarks/results/vulkan-<timestamp>.json`, using the schema from Task 1 and `backend: "vulkan-whisper-cpp"`. Include GPU device name and software version only when explicitly reported by the tool. Do not estimate timing from logs.

**Step 6: Validate output and host stability**

Require:

```bash
test -s benchmarks/results/vulkan-*.txt
python3 -m json.tool benchmarks/results/vulkan-*.json
```

Also capture a bounded post-run `dmesg`/kernel-log query for `amdgpu`, GPU reset, or hang events, redacting unrelated content. G3 passes only if no GPU reset/hang and transcript is non-empty.

**Step 7: Record and commit only code/docs**

Record command versions, model quantization, exact exit status, wall time, RTF, and G2/G3 decision in the dated R&D markdown. Do not commit generated models, fixture copies, raw transcript, or benchmark metrics unless the user explicitly requests it.

```bash
git add benchmarks/run_vulkan_benchmark.sh docs/rnd/amd-vulkan-benchmark-YYYY-MM-DD.md
git commit -m "docs: record isolated AMD Vulkan whisper benchmark"
```

---

### Task 5: Compare GPU result against CPU and make an adoption decision

**Objective:** Decide whether to stop, repeat a constrained benchmark, or design an optional backend—without silently migrating production.

**Files:**
- Create: `benchmarks/compare_results.py`
- Create: `tests/test_compare_benchmark_results.py`
- Create: `docs/rnd/amd-vulkan-decision.md`

**Step 1: Write failing comparison tests**

Test that comparison rejects mismatched fixture SHA-256, compares only runs with the same model class/language where possible, calculates speedup from recorded wall times, and labels quality as `manual_review_required` rather than asserting equality from text hashes.

**Step 2: Implement comparison**

`benchmarks/compare_results.py` must produce a small report containing:

- CPU/GPU model and backend,
- wall seconds and RTF,
- calculated speedup,
- transcript byte/hash metadata,
- explicit `manual_review_required` field,
- decision recommendation constrained to `stop`, `repeat`, or `design-optional-backend`.

**Step 3: Run comparison and manual sample review**

Use the CPU and Vulkan JSON only if the fixture checksums match. Review a short fixed transcript segment manually for Indonesian correctness; do not publish the full transcript if fixture policy disallows it.

**Step 4: Apply decision criteria**

- `stop`: GPU unavailable, crash/reset, functional failure, or no performance benefit.
- `repeat`: functional but a confounder exists (cold model load, mismatch in model/quantization, invalid timing, or unknown VRAM pressure).
- `design-optional-backend`: G1–G5 all pass, including the agreed >=20% gain and no stability issue.

Commit comparison tooling and decision document:

```bash
git add benchmarks/compare_results.py tests/test_compare_benchmark_results.py docs/rnd/amd-vulkan-decision.md
git commit -m "docs: decide AMD Vulkan transcription viability"
```

---

### Task 6: Design only, conditional on a positive R&D decision

**Objective:** Prepare a narrowly scoped production integration proposal without implementing/redeploying it.

**Files:**
- Create: `.hermes/plans/YYYY-MM-DD_HHMMSS-optional-whisper-vulkan-backend.md`
- Do not modify application or deployment files in this task.

**Step 1: Map the current contract**

Inspect and cite:

- `src/core/engine.py` (`TranscribeEngine` model loading and output contract),
- `src/web/server.py` (job configuration currently hard-coding CPU/int8),
- `src/utils/config.py` (persisted settings defaults),
- `tests/test_engine_smoke.py`, `tests/test_regressions.py`, `tests/test_wdac_patch.py`, and job-store tests.

**Step 2: Specify a backend adapter boundary**

The future adapter must preserve job state transitions, cancellation behavior, output filenames, transcript writer contract, language/model validation, and user isolation. Backend choice must be server-controlled initially—no user-facing GPU toggle until quotas, concurrency, and fallback behavior are tested.

**Step 3: Specify safe rollout design**

Propose, but do not execute:

- `TRANSCRIBE_BACKEND=cpu-faster-whisper|vulkan-whisper-cpp`, default CPU;
- mutually exclusive runtime profiles/services, not a dual writer;
- one GPU job at a time;
- automatic CPU fallback only for clearly classified startup/availability failure, never after a partial output without preserving error evidence;
- metrics/log fields that contain no filename/audio content;
- explicit rollback to CPU by configuration plus recreate of only the `transcribe` service after separately approved smoke test.

**Step 4: Define acceptance tests and approval gates**

Include CPU regression suite, isolated GPU image build, one authorized test job, output contract comparison, subpath/public route smoke test, GPU process-device verification, and rollback test. Keep build, isolated smoke test, and production recreate as separate user approval gates.

---

## Overall validation checklist

- [ ] Git status confirms no current untracked release artifacts were edited.
- [ ] Production `mesin-transcribe` and proxy were never rebuilt/recreated during R&D.
- [ ] No production `data/`, SQLite database, models cache, `.env`, or uploads were mounted writable or modified.
- [ ] Fixture is non-sensitive and its SHA-256 matches CPU/GPU comparison.
- [ ] GPU benchmark image is unprivileged, no-port, one-shot, with only `/dev/dri`, read-only fixture, and isolated result/model mounts.
- [ ] GPU result proves actual AMD Vulkan hardware, not lavapipe/software fallback.
- [ ] Exact CPU and GPU timings were captured from tool output; no estimated results.
- [ ] Stability evidence includes a bounded driver error check after run.
- [ ] No production backend adoption occurs unless G1–G5 pass and user explicitly approves a separate implementation plan.

## Risks and tradeoffs

- RX 570 (Polaris) is supported by Mesa RADV Vulkan but is older hardware. A functional Vulkan run may still be slower than optimized CPU `int8`, especially for a small audio input or first-run model loading.
- `whisper.cpp` model formats/quantizations differ from faster-whisper/CTranslate2. Direct transcript equality is not a valid criterion; assess output contract and a fixed manual quality sample.
- Passing `/dev/dri` into any container increases hardware access; the benchmark must remain no-port, unprivileged, non-root, one-shot, and isolated from user data.
- VRAM availability and Mesa version can materially alter results; record both in every benchmark report.
- A CPU fallback is a product/runtime design decision, not an R&D shortcut. Do not introduce it until output and job-state contracts are covered by tests.

## Open questions to resolve at the G5 review

1. What is the actual RX 570 VRAM capacity reported by Vulkan?
2. Does `small` Vulkan meaningfully beat current CPU `small`/`int8` on warm runs, not merely cold model-download conditions?
3. Is `medium` functional and stable within available VRAM, and is it actually needed for the app’s quality target?
4. Should a successful optional GPU backend be limited to admins/internal jobs first, or can it safely use existing queue semantics?
5. Does the current CPU benchmark use a comparable model/quality setting; if not, what comparison model pair is acceptable?
