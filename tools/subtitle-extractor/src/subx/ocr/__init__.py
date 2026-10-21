from __future__ import annotations

from .base import OCRBackend


def create_backend(engine: str, lang: str) -> OCRBackend:
    if engine == "paddle":
        from .paddle_backend import PaddleBackend

        return PaddleBackend(lang=lang)
    if engine == "onnx":
        from .onnx_backend import OnnxBackend

        return OnnxBackend(lang=lang)
    raise ValueError(f"Unsupported engine: {engine}")
