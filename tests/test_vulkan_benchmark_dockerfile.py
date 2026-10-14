"""Static safety and reproducibility checks for the Vulkan benchmark image."""

from pathlib import Path


DOCKERFILE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "Dockerfile.whisper-vulkan"
)


def _text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_vulkan_benchmark_dockerfile_pins_whisper_cpp_revision():
    text = _text()

    assert "ARG WHISPER_CPP_REV=0c7be696371069e0baa2515ed7aa08d5a5473aa6" in text
    assert "git checkout --detach \"${WHISPER_CPP_REV}\"" in text


def test_vulkan_benchmark_dockerfile_builds_vulkan_cli_without_production_files():
    text = _text()

    assert "-DGGML_VULKAN=1" in text
    assert "--target whisper-cli" in text
    assert "ENTRYPOINT [\"/opt/whisper.cpp/build/bin/whisper-cli\"]" in text
    assert "COPY ." not in text
    assert "/data" not in text
    assert ".env" not in text
