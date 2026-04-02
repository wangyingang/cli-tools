from __future__ import annotations

from .base import OCRBackend
from .onnx_backend import OnnxBackend
from .paddle_backend import PaddleBackend


def create_backend(engine: str, lang: str) -> OCRBackend:
    if engine == "paddle":
        return PaddleBackend(lang=lang)
    if engine == "onnx":
        return OnnxBackend(lang=lang)
    raise ValueError(f"Unsupported engine: {engine}")
