from __future__ import annotations

import io
import os
import warnings
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout

from .base import OCRBackend
from .paddle_models import (
    PP_OCR_V5_SERVER_DET_REPO,
    PP_OCR_V5_SERVER_REC_REPO,
    download_model_snapshot,
    ensure_huggingface_hub_cache,
)
from ..text import normalize_text
from ..types import OCRText


class PaddleBackend(OCRBackend):
    engine_name = "paddle"

    def __init__(self, lang: str) -> None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        cache_dir = ensure_huggingface_hub_cache()
        det_dir = download_model_snapshot(PP_OCR_V5_SERVER_DET_REPO, cache_dir=cache_dir)
        rec_dir = download_model_snapshot(PP_OCR_V5_SERVER_REC_REPO, cache_dir=cache_dir)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    from paddleocr import PaddleOCR
                    self._ocr = PaddleOCR(
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_detection_model_dir=str(det_dir),
                        text_recognition_model_dir=str(rec_dir),
                    )
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install project dependencies with a Python 3.12 environment."
            ) from exc

        self.lang = lang

    def recognize(self, image) -> OCRText:
        prediction = self._ocr.predict(image)
        payload = _extract_payload(prediction)
        texts = [normalize_text(str(text)) for text in payload.get("rec_texts", []) if normalize_text(str(text))]
        scores = [float(score) for score in payload.get("rec_scores", [])[: len(texts)]]
        if not texts and "texts" in payload:
            texts = [normalize_text(str(text)) for text in payload.get("texts", []) if normalize_text(str(text))]
            scores = [float(score) for score in payload.get("scores", [])[: len(texts)]]
        merged = "\n".join(texts).strip()
        score = sum(scores) / len(scores) if scores else 0.0
        return OCRText(text=merged, score=score, lines=texts)


def _extract_payload(prediction) -> Mapping[str, object]:
    if isinstance(prediction, list):
        if not prediction:
            return {}
        candidate = prediction[0]
    else:
        candidate = prediction

    if isinstance(candidate, Mapping):
        return candidate.get("res", candidate)

    for attr in ("res", "json", "data"):
        value = getattr(candidate, attr, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if isinstance(value, Mapping):
            return value.get("res", value)
    return {}
