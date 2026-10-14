# Checkpoint R&D — AMD Vulkan Whisper Build

**Status:** paused; no production change

## Objective

Assess whether the BTD server AMD Radeon RX 570 can run an isolated `whisper.cpp` Vulkan benchmark before any optional-backend design or production migration.

## Production safety status

- `mesin-transcribe` was never rebuilt, recreated, or configured differently.
- Production remained healthy with zero restarts during this R&D checkpoint.
- No production `data/`, SQLite state, uploads, results, models cache, or `.env` was mounted into the R&D service.
- No R&D benchmark container was run.

## Verified hardware/runtime facts

- Host GPU: XFX AMD Radeon RX 570 (Polaris/Ellesmere; PCI ID `1002:67df`).
- Kernel driver: `amdgpu`.
- Radeon Vulkan ICD exists: `/usr/share/vulkan/icd.d/radeon_icd.json`.
- Render node: `/dev/dri/renderD128`, owned `root:render`, mode `660`.
- Deployment user `magangbtd` is not in group `render`, so host Vulkan run under that user falls back to llvmpipe/software.
- Production transcriber container has no `/dev/dri` mapping and intentionally remains CPU-only.

## R&D workspace and artifacts

Remote R&D-only workspace:

```text
/home/magangbtd/firmware_transcribe-rnd-vulkan
```

Transferred and SHA-256-verified items:

- `benchmarks/Dockerfile.whisper-vulkan`
- `benchmarks/docker-compose.vulkan-benchmark.yml`
- `sample_audio/sample_75s.mp3` (non-sensitive fixture)

The macOS metadata file `sample_audio/._sample_75s.mp3` was removed from the R&D workspace before build.

## Local commits

- `a1395cd` — isolated Vulkan benchmark Compose guardrails and R&D plan.
- `1fbc7ba` — pinned `whisper.cpp` Vulkan benchmark image definition.
- `6e4ed77` — add `spirv-headers` dependency required by CMake configuration.

Static guardrail tests passed locally: `5 passed`.

## Build result and blocker

The image build reached C++ compilation of the Vulkan backend but failed. The source revision pinned for reproducibility was:

```text
whisper.cpp 0c7be696371069e0baa2515ed7aa08d5a5473aa6
```

The base image was `debian:bookworm-slim` with Debian Bookworm Vulkan headers.

The decisive compiler errors in `ggml-vulkan.cpp` were:

```text
error: 'LayerSettingEXT' is not a member of 'vk'
error: 'vk::LayerSettingTypeEXT' has not been declared
error: 'LayerSettingsCreateInfoEXT' is not a member of 'vk'
```

Conclusion: the pinned current `whisper.cpp` Vulkan code expects the newer `VK_EXT_layer_settings` header/API, while Debian Bookworm’s Vulkan headers are too old. This is a build-toolchain compatibility issue; it does not establish a GPU driver or RX 570 incompatibility.

## Deferred decision / next R&D gate

Before any new build, inspect the pinned upstream source and CMake options to determine the narrowest compatible route:

1. Disable the `VK_EXT_layer_settings` code path if upstream exposes a supported build option.
2. Build the same pinned source with a newer Vulkan headers/toolchain base image.
3. Pin `whisper.cpp` to a verified older revision compatible with Bookworm headers.

Selection requirements:

- retain the unprivileged, no-port, read-only benchmark isolation;
- retain explicit `/dev/dri` and temporary `render`-GID access only for the R&D container;
- do not modify the host user’s permanent group membership;
- build image first, then separately approve/run a GPU enumeration probe;
- do not run transcription or modify production until actual AMD hardware enumeration is verified (not llvmpipe).

## Open items

- Check actual RX 570 VRAM only after a hardware Vulkan container probe succeeds.
- Compare CPU and GPU speed only after an actual AMD Vulkan run succeeds.
- Do not design production fallback/adapter integration before the benchmark decision gate.
