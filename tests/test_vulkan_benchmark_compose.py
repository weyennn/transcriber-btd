"""Guardrails for the isolated AMD Vulkan benchmark service."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "benchmarks" / "docker-compose.vulkan-benchmark.yml"


def _service() -> dict:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return compose["services"]["whisper-vulkan-benchmark"]


def test_vulkan_benchmark_has_no_network_or_production_lifecycle_settings():
    service = _service()

    assert "ports" not in service
    assert "container_name" not in service
    assert "restart" not in service
    assert "depends_on" not in service
    assert service["read_only"] is True
    assert service["user"] == "${BENCHMARK_UID:?}:${BENCHMARK_GID:?}"


def test_vulkan_benchmark_mounts_only_fixture_readonly_and_results_writable():
    volumes = _service()["volumes"]

    assert volumes == [
        "../sample_audio:/fixtures:ro",
        "../benchmarks/results:/results",
        "../benchmarks/model-cache:/models",
    ]
    assert all("data" not in volume for volume in volumes)
    assert all(".env" not in volume for volume in volumes)
    assert all("uploads" not in volume for volume in volumes)
    assert all("docker.sock" not in volume for volume in volumes)


def test_vulkan_benchmark_has_only_render_device_and_required_render_group():
    service = _service()

    assert service["devices"] == ["/dev/dri:/dev/dri"]
    assert service["group_add"] == ["${RENDER_GID:?RENDER_GID is required}"]
    assert service["privileged"] is False
    assert service["environment"]["VK_ICD_FILENAMES"] == "/usr/share/vulkan/icd.d/radeon_icd.json"
