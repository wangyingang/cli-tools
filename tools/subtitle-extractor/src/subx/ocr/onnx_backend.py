from __future__ import annotations

from pathlib import Path

from .base import OCRBackend
from ..text import normalize_text
from ..types import OCRText


class OnnxBackend(OCRBackend):
    engine_name = "onnx"
    repo_id = "monkt/paddleocr-onnx"

    def __init__(self, lang: str) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "rapidocr-onnxruntime is not installed. Install project dependencies to use the ONNX backend."
            ) from exc

        det_path = _download(self.repo_id, "detection/v5/det.onnx")
        rec_folder = "languages/chinese" if lang in {"zh", "mixed"} else "languages/english"
        rec_path = _download(self.repo_id, f"{rec_folder}/rec.onnx")
        dict_path = _download(self.repo_id, f"{rec_folder}/dict.txt")
        self._ocr = RapidOCR(
            det_model_path=str(det_path),
            rec_model_path=str(rec_path),
            rec_keys_path=str(dict_path),
        )

    def recognize(self, image) -> OCRText:
        result, _elapsed = self._ocr(image)
        if not result:
            return OCRText(text="", score=0.0, lines=[])

        lines: list[str] = []
        scores: list[float] = []
        for item in result:
            if len(item) < 3:
                continue
            text = normalize_text(str(item[1]))
            if not text:
                continue
            lines.append(text)
            scores.append(float(item[2]))
        merged = "\n".join(lines).strip()
        score = sum(scores) / len(scores) if scores else 0.0
        return OCRText(text=merged, score=score, lines=lines)


def _download(repo_id: str, filename: str) -> Path:
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(repo_id=repo_id, filename=filename))
