from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

PP_OCR_V5_SERVER_DET_REPO = "PaddlePaddle/PP-OCRv5_server_det"
PP_OCR_V5_SERVER_REC_REPO = "PaddlePaddle/PP-OCRv5_server_rec"


def ensure_huggingface_hub_cache() -> str:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    if cache_home:
        hub_cache = Path(cache_home) / "huggingface" / "hub"
    else:
        hub_cache = Path.home() / ".cache" / "huggingface" / "hub"
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hub_cache))
    return os.environ["HUGGINGFACE_HUB_CACHE"]


def download_model_snapshot(repo_id: str, *, cache_dir: str | None = None) -> Path:
    from huggingface_hub import snapshot_download

    resolved_cache_dir = cache_dir or ensure_huggingface_hub_cache()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return Path(snapshot_download(repo_id=repo_id, cache_dir=resolved_cache_dir))
