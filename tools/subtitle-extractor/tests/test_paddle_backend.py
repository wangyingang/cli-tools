import io
import os
import sys
import types
import unittest
from pathlib import Path
import warnings
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import call, patch

from subx.ocr.paddle_backend import PaddleBackend


class PaddleBackendTests(unittest.TestCase):
    @patch("huggingface_hub.snapshot_download")
    def test_init_downloads_model_dirs_from_hf_and_passes_dirs(
        self, snapshot_download
    ) -> None:
        det_dir = "/tmp/hf-cache/models--PaddlePaddle--PP-OCRv5_server_det/snapshots/det"
        rec_dir = "/tmp/hf-cache/models--PaddlePaddle--PP-OCRv5_server_rec/snapshots/rec"
        snapshot_download.side_effect = [det_dir, rec_dir]

        captured_kwargs: dict[str, object] = {}

        def fake_paddle_ocr(**kwargs):
            captured_kwargs.update(kwargs)
            return object()

        fake_module = types.SimpleNamespace(PaddleOCR=fake_paddle_ocr)
        xdg_cache_home = "/tmp/xdg-cache"
        expected_hf_cache = str(Path(xdg_cache_home) / "huggingface" / "hub")

        with patch.dict(os.environ, {"XDG_CACHE_HOME": xdg_cache_home}, clear=True):
            with patch.dict(sys.modules, {"paddleocr": fake_module}):
                PaddleBackend("zh")
            self.assertEqual(os.environ.get("HUGGINGFACE_HUB_CACHE"), expected_hf_cache)

        self.assertEqual(
            snapshot_download.call_args_list,
            [
                call(
                    repo_id="PaddlePaddle/PP-OCRv5_server_det",
                    cache_dir=expected_hf_cache,
                ),
                call(
                    repo_id="PaddlePaddle/PP-OCRv5_server_rec",
                    cache_dir=expected_hf_cache,
                ),
            ],
        )
        self.assertEqual(captured_kwargs.get("text_detection_model_dir"), det_dir)
        self.assertEqual(captured_kwargs.get("text_recognition_model_dir"), rec_dir)
        self.assertNotIn("text_detection_model_name", captured_kwargs)
        self.assertNotIn("text_recognition_model_name", captured_kwargs)

    @patch("huggingface_hub.snapshot_download")
    def test_init_defaults_hf_cache_to_xdg_like_location(self, snapshot_download) -> None:
        snapshot_download.side_effect = [
            "/tmp/hf-cache/det",
            "/tmp/hf-cache/rec",
        ]

        fake_module = types.SimpleNamespace(PaddleOCR=lambda **_kwargs: object())
        expected_hf_cache = str(Path.home() / ".cache" / "huggingface" / "hub")

        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(sys.modules, {"paddleocr": fake_module}):
                PaddleBackend("zh")
            self.assertEqual(os.environ.get("HUGGINGFACE_HUB_CACHE"), expected_hf_cache)

        self.assertEqual(
            snapshot_download.call_args_list,
            [
                call(
                    repo_id="PaddlePaddle/PP-OCRv5_server_det",
                    cache_dir=expected_hf_cache,
                ),
                call(
                    repo_id="PaddlePaddle/PP-OCRv5_server_rec",
                    cache_dir=expected_hf_cache,
                ),
            ],
        )

    @patch("huggingface_hub.snapshot_download", side_effect=["/tmp/hf-cache/det", "/tmp/hf-cache/rec"])
    def test_init_suppresses_noisy_library_output(self, _snapshot_download) -> None:
        def fake_paddle_ocr(**_kwargs):
            print("Checking connectivity to the model hosters, this may take a while.")
            print("Creating model: ('PP-OCRv5_server_det', None)", file=sys.stderr)
            warnings.warn("`lang` and `ocr_version` will be ignored when model names are set.")
            return object()

        fake_module = types.SimpleNamespace(PaddleOCR=fake_paddle_ocr)
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with patch.dict(sys.modules, {"paddleocr": fake_module}):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    PaddleBackend("zh")

        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(stderr_buffer.getvalue(), "")
        self.assertEqual(caught, [])

    @patch("huggingface_hub.snapshot_download")
    def test_init_suppresses_noisy_huggingface_download_output(
        self, snapshot_download
    ) -> None:
        def fake_snapshot_download(*, repo_id, **_kwargs):
            print(f"Fetching files for {repo_id}", file=sys.stderr)
            return f"/tmp/hf-cache/{repo_id.rsplit('/', 1)[-1]}"

        snapshot_download.side_effect = fake_snapshot_download
        fake_module = types.SimpleNamespace(PaddleOCR=lambda **_kwargs: object())
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with patch.dict(sys.modules, {"paddleocr": fake_module}):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                PaddleBackend("zh")

        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(stderr_buffer.getvalue(), "")

    @patch("huggingface_hub.snapshot_download", side_effect=["/tmp/hf-cache/det", "/tmp/hf-cache/rec"])
    def test_init_sets_model_source_env_before_import(self, _snapshot_download) -> None:
        fake_module = types.SimpleNamespace(PaddleOCR=lambda **_kwargs: object())
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "paddleocr":
                self.assertEqual(os.environ.get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"), "True")
                return fake_module
            return original_import(name, globals, locals, fromlist, level)

        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.__import__", side_effect=fake_import):
                PaddleBackend("zh")

    @patch("huggingface_hub.snapshot_download", side_effect=["/tmp/hf-cache/det", "/tmp/hf-cache/rec"])
    def test_init_suppresses_noisy_import_output(self, _snapshot_download) -> None:
        fake_module = types.SimpleNamespace(PaddleOCR=lambda **_kwargs: object())
        original_import = __import__
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "paddleocr":
                print("Connectivity check to the model hoster has been skipped.")
                print("Model files already exist.", file=sys.stderr)
                return fake_module
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                PaddleBackend("zh")

        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertEqual(stderr_buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
