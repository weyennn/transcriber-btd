"""Guardrails: production compose memakai GPU NVIDIA/CUDA, sama seperti Doclingo."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_transcribe_production_requests_nvidia_gpu_and_cuda_runtime():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["transcribe"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert service["gpus"] == "all"
    assert service["environment"]["TRANSCRIBE_DEVICE"] == "${TRANSCRIBE_DEVICE:-cuda}"
    assert service["environment"]["TRANSCRIBE_COMPUTE_TYPE"] == "${TRANSCRIBE_COMPUTE_TYPE:-float16}"
    assert "FROM nvidia/cuda:12.4.1-base-ubuntu22.04" in dockerfile
    assert "nvidia-cudnn-cu12" in dockerfile
    assert "nvidia-cublas-cu12" in dockerfile
    assert compose["services"]["transcribe"]["build"]["pull"] is False
