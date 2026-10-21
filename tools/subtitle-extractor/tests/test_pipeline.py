import io
import sys
import types
import unittest
from pathlib import Path
from contextlib import redirect_stderr
from unittest.mock import patch

import cv2

from subx.pipeline import Checkpoint, ExtractConfig, _OverallProgressReporter, extract_subtitles
from subx.pipeline import _collect_checkpoints
from subx.types import OCRText, PipelineStats


class PipelineTests(unittest.TestCase):
    class _FakeProgressReporter:
        def __init__(self) -> None:
            self.updates: list[int] = []
            self.closed = False

        def update(self, amount: int = 1) -> None:
            self.updates.append(amount)

        def close(self) -> None:
            self.closed = True

    class _RecordingProcessPoolExecutor:
        instances: list["PipelineTests._RecordingProcessPoolExecutor"] = []

        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs
            self.map_calls: list[list[tuple[int, str]]] = []
            self.closed = False
            self.shutdown_calls = 0
            self.__class__.instances.append(self)

        @classmethod
        def reset(cls) -> None:
            cls.instances = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.closed = True

        def map(self, fn, items):
            del fn
            batch = list(items)
            self.map_calls.append(batch)
            return [
                (index, OCRText(text=f"text-{index}", score=1.0, lines=[f"text-{index}"]))
                for index, _image in batch
            ]

        def shutdown(self, wait=True):
            del wait
            self.shutdown_calls += 1
            self.closed = True

    class _FakeVideoCapture:
        def __init__(self, frames: list[object], fps: float = 25.0) -> None:
            self._frames = frames
            self._fps = fps
            self._index = 0
            self._grabbed_index: int | None = None
            self.released = False

        def isOpened(self) -> bool:
            return True

        def read(self):
            if self._index >= len(self._frames):
                return False, None
            frame = self._frames[self._index]
            self._index += 1
            self._grabbed_index = self._index - 1
            return True, frame

        def grab(self):
            if self._index >= len(self._frames):
                self._grabbed_index = None
                return False
            self._grabbed_index = self._index
            self._index += 1
            return True

        def retrieve(self):
            if self._grabbed_index is None:
                return False, None
            frame = self._frames[self._grabbed_index]
            return True, frame

        def get(self, prop):
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return len(self._frames)
            if prop == cv2.CAP_PROP_FPS:
                return self._fps
            if prop == cv2.CAP_PROP_POS_MSEC:
                return max(self._index - 1, 0) * 1000.0 / self._fps
            return 0.0

        def release(self):
            self.released = True

    class _GrabRetrieveVideoCapture:
        def __init__(self, frames: list[object], fps: float = 25.0) -> None:
            self._frames = frames
            self._fps = fps
            self._index = 0
            self._last_grabbed_index: int | None = None
            self.released = False
            self.grab_calls: list[int] = []
            self.retrieve_calls: list[int] = []
            self.read_calls = 0

        def isOpened(self) -> bool:
            return True

        def grab(self) -> bool:
            if self._index >= len(self._frames):
                return False
            self.grab_calls.append(self._index)
            self._last_grabbed_index = self._index
            self._index += 1
            return True

        def retrieve(self):
            if self._last_grabbed_index is None:
                return False, None
            self.retrieve_calls.append(self._last_grabbed_index)
            frame = self._frames[self._last_grabbed_index]
            return True, frame

        def read(self):
            self.read_calls += 1
            raise AssertionError("read() should not be used when grab()/retrieve() is available")

        def get(self, prop):
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return len(self._frames)
            if prop == cv2.CAP_PROP_FPS:
                return self._fps
            if prop == cv2.CAP_PROP_POS_MSEC:
                index = self._last_grabbed_index
                if index is None:
                    index = max(self._index - 1, 0)
                return index * 1000.0 / self._fps
            return 0.0

        def release(self):
            self.released = True

    def setUp(self) -> None:
        self._RecordingProcessPoolExecutor.reset()

    def test_extract_subtitles_flushes_pending_ocr_batches(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=1,
            max_pending_ocr_frames=2,
        )

        def fake_collect(config_arg, on_candidate=None, progress_reporter=None):
            self.assertIsNotNone(on_candidate)
            self.assertIsNotNone(progress_reporter)
            progress_reporter.start(3)
            on_candidate(0, "frame-0")
            on_candidate(1, "frame-1")
            on_candidate(2, "frame-2")
            checkpoints = [
                Checkpoint(index=0, time_seconds=0.0, frame_changed=True),
                Checkpoint(index=1, time_seconds=1.0, frame_changed=True),
                Checkpoint(index=2, time_seconds=2.0, frame_changed=True),
            ]
            stats = PipelineStats(sampled_frames=3, submitted_ocr_frames=3)
            return checkpoints, stats

        calls: list[list[tuple[int, str]]] = []

        def fake_run_ocr_candidates(candidates, _config, backend=None, executor=None):
            self.assertIsNone(executor)
            calls.append(list(candidates))
            return {
                index: OCRText(text=f"text-{index}", score=1.0, lines=[f"text-{index}"])
                for index, _image in candidates
            }

        with patch("subx.pipeline._collect_checkpoints", side_effect=fake_collect):
            with patch("subx.pipeline._run_ocr_candidates", side_effect=fake_run_ocr_candidates):
                with patch("subx.pipeline.create_backend"):
                    result = extract_subtitles(config)

        self.assertEqual(calls, [[(0, "frame-0"), (1, "frame-1")], [(2, "frame-2")]])
        self.assertEqual(result.stats.submitted_ocr_frames, 3)

    def test_extract_subtitles_uses_single_reporter_for_sampling_and_flushes(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=1,
            max_pending_ocr_frames=2,
        )
        reporter = self._FakeProgressReporter()

        def fake_collect(config_arg, on_candidate=None, progress_reporter=None):
            self.assertIsNotNone(on_candidate)
            self.assertIs(progress_reporter, reporter)
            on_candidate(0, "frame-0")
            on_candidate(1, "frame-1")
            on_candidate(2, "frame-2")
            checkpoints = [
                Checkpoint(index=0, time_seconds=0.0, frame_changed=True),
                Checkpoint(index=1, time_seconds=1.0, frame_changed=True),
                Checkpoint(index=2, time_seconds=2.0, frame_changed=True),
            ]
            stats = PipelineStats(sampled_frames=3, submitted_ocr_frames=3)
            return checkpoints, stats

        def fake_run_ocr_candidates(candidates, _config, backend=None, executor=None):
            self.assertIsNone(executor)
            return {
                index: OCRText(text=f"text-{index}", score=1.0, lines=[f"text-{index}"])
                for index, _image in candidates
            }

        def forbidden_tqdm(*_args, **_kwargs):
            raise AssertionError("progress should be driven by a single reporter, not a nested tqdm")

        fake_tqdm_module = types.SimpleNamespace(tqdm=forbidden_tqdm)
        stderr = io.StringIO()

        with patch.dict(sys.modules, {"tqdm": fake_tqdm_module}):
            with patch("subx.pipeline._collect_checkpoints", side_effect=fake_collect):
                with patch("subx.pipeline._run_ocr_candidates", side_effect=fake_run_ocr_candidates):
                    with patch("subx.pipeline.create_backend"):
                        with redirect_stderr(stderr):
                            extract_subtitles(config, progress_reporter=reporter)

        self.assertEqual(reporter.updates, [1, 1, 1])
        self.assertTrue(reporter.closed)
        self.assertNotIn("OCR (", stderr.getvalue())

    def test_extract_subtitles_closes_reporter_after_ocr_flush(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=1,
            max_pending_ocr_frames=2,
        )
        reporter = self._FakeProgressReporter()

        def fake_collect(config_arg, on_candidate=None, progress_reporter=None):
            self.assertIsNotNone(on_candidate)
            self.assertIs(progress_reporter, reporter)
            on_candidate(0, "frame-0")
            checkpoints = [
                Checkpoint(index=0, time_seconds=0.0, frame_changed=True),
            ]
            stats = PipelineStats(sampled_frames=1, submitted_ocr_frames=1)
            return checkpoints, stats

        def fake_run_ocr_candidates(candidates, _config, backend=None, executor=None):
            self.assertIsNone(executor)
            return {
                index: OCRText(text=f"text-{index}", score=1.0, lines=[f"text-{index}"])
                for index, _image in candidates
            }

        def forbidden_tqdm(*_args, **_kwargs):
            raise AssertionError("progress should be driven by a single reporter, not a nested tqdm")

        fake_tqdm_module = types.SimpleNamespace(tqdm=forbidden_tqdm)

        with patch.dict(sys.modules, {"tqdm": fake_tqdm_module}):
            with patch("subx.pipeline._collect_checkpoints", side_effect=fake_collect):
                with patch("subx.pipeline._run_ocr_candidates", side_effect=fake_run_ocr_candidates):
                    with patch("subx.pipeline.create_backend"):
                        extract_subtitles(config, progress_reporter=reporter)

        self.assertTrue(reporter.closed)

    def test_extract_subtitles_reuses_single_worker_backend_across_batches(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=1,
            max_pending_ocr_frames=2,
        )

        def fake_collect(config_arg, on_candidate=None, progress_reporter=None):
            self.assertIsNotNone(on_candidate)
            self.assertIsNotNone(progress_reporter)
            for index in range(5):
                on_candidate(index, f"frame-{index}")
            checkpoints = [
                Checkpoint(index=index, time_seconds=float(index), frame_changed=True)
                for index in range(5)
            ]
            stats = PipelineStats(sampled_frames=5, submitted_ocr_frames=5)
            return checkpoints, stats

        class FakeBackend:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def recognize(self, image):
                self.calls.append(image)
                index = len(self.calls) - 1
                return OCRText(text=f"text-{index}", score=1.0, lines=[f"text-{index}"])

        backend = FakeBackend()

        with patch("subx.pipeline._collect_checkpoints", side_effect=fake_collect):
            with patch("subx.pipeline.create_backend", return_value=backend) as create_backend:
                extract_subtitles(config)

        self.assertEqual(create_backend.call_count, 1)
        self.assertEqual(backend.calls, [f"frame-{index}" for index in range(5)])

    def test_extract_subtitles_reuses_one_process_pool_executor_across_ocr_flushes(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=2,
            max_pending_ocr_frames=2,
        )

        def fake_collect(config_arg, on_candidate=None, progress_reporter=None):
            self.assertIsNotNone(on_candidate)
            self.assertIsNotNone(progress_reporter)
            for index in range(5):
                on_candidate(index, f"frame-{index}")
            checkpoints = [
                Checkpoint(index=index, time_seconds=float(index), frame_changed=True)
                for index in range(5)
            ]
            stats = PipelineStats(sampled_frames=5, submitted_ocr_frames=5)
            return checkpoints, stats

        self._RecordingProcessPoolExecutor.reset()

        with patch("subx.pipeline._collect_checkpoints", side_effect=fake_collect):
            with patch("subx.pipeline.ProcessPoolExecutor", new=self._RecordingProcessPoolExecutor):
                extract_subtitles(config)

        self.assertEqual(len(self._RecordingProcessPoolExecutor.instances), 1)
        executor = self._RecordingProcessPoolExecutor.instances[0]
        self.assertEqual(len(executor.map_calls), 3)
        self.assertEqual(executor.shutdown_calls, 1)

    def test_extract_subtitles_progress_total_tracks_queued_ocr_work(self) -> None:
        totals: list[int] = []

        class FakeTqdm:
            def __init__(self, *, total, unit, mininterval, desc):
                del unit, mininterval, desc
                self._total = total
                totals.append(total)

            @property
            def total(self):
                return self._total

            @total.setter
            def total(self, value):
                self._total = value
                totals.append(value)

            def update(self, amount):
                del amount

            def set_postfix_str(self, *_args, **_kwargs):
                pass

            def refresh(self):
                pass

            def close(self):
                pass

        fake_tqdm_module = types.SimpleNamespace(tqdm=FakeTqdm)

        with patch.dict(sys.modules, {"tqdm": fake_tqdm_module}):
            reporter = _OverallProgressReporter(sample_every=3)
            reporter.start(3)
            reporter.queue_ocr()
            reporter.queue_ocr()
            reporter.queue_ocr()
            reporter.finish_sampling()

        self.assertEqual(totals[0], 3)
        self.assertEqual(totals[-1], 6)
        self.assertEqual(totals, sorted(totals))

    def test_collect_checkpoints_skips_redundant_ocr_candidate_when_similarity_is_high(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=1,
            workers=1,
            max_pending_ocr_frames=2,
        )
        object.__setattr__(config, "ocr_candidate_similarity_threshold", 0.97)
        frame_a = object()
        frame_b = object()
        fake_capture = self._FakeVideoCapture([frame_a, frame_b])
        on_candidate_calls: list[tuple[int, object]] = []

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{id(roi_frame)}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return roi_frame

        def fake_visually_similar(previous, current, diff_threshold):
            score = fake_similarity_score(previous, current)
            return score < diff_threshold

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.99

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True) as similarity_score:
                                checkpoints, stats = _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        self.assertEqual(similarity_score.call_count, 1)
        self.assertEqual(on_candidate_calls, [(0, frame_a)])
        self.assertEqual(stats.sampled_frames, 2)
        self.assertEqual(stats.submitted_ocr_frames, 1)
        self.assertEqual(stats.reused_frames, 1)
        self.assertEqual([checkpoint.frame_changed for checkpoint in checkpoints], [True, False])

    def test_collect_checkpoints_keeps_distinct_ocr_candidate_when_similarity_is_low(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=1,
            workers=1,
            max_pending_ocr_frames=2,
        )
        object.__setattr__(config, "ocr_candidate_similarity_threshold", 0.97)
        frame_a = object()
        frame_b = object()
        fake_capture = self._FakeVideoCapture([frame_a, frame_b])
        on_candidate_calls: list[tuple[int, object]] = []

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{id(roi_frame)}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return roi_frame

        def fake_visually_similar(previous, current, diff_threshold):
            score = fake_similarity_score(previous, current)
            return score < diff_threshold

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.10

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True) as similarity_score:
                                checkpoints, stats = _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        self.assertEqual(similarity_score.call_count, 1)
        self.assertEqual(on_candidate_calls, [(0, frame_a), (1, frame_b)])
        self.assertEqual(stats.sampled_frames, 2)
        self.assertEqual(stats.submitted_ocr_frames, 2)
        self.assertEqual(stats.reused_frames, 0)
        self.assertEqual([checkpoint.frame_changed for checkpoint in checkpoints], [True, True])

    def test_collect_checkpoints_debounces_long_changed_runs_by_default(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            workers=1,
            max_pending_ocr_frames=2,
        )
        fake_capture = self._FakeVideoCapture(list(range(19)))
        on_candidate_calls: list[tuple[int, object]] = []
        visually_similar_flags = [False] * 6

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{roi_frame}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return roi_frame

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return visually_similar_flags.pop(0)

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.0

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                                checkpoints, stats = _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        self.assertEqual(stats.sampled_frames, 7)
        self.assertLess(len(on_candidate_calls), stats.sampled_frames)
        self.assertGreaterEqual(len(on_candidate_calls), 1)
        self.assertEqual(on_candidate_calls[0][0], 0)
        self.assertEqual(stats.submitted_ocr_frames, len(on_candidate_calls))
        self.assertEqual(len([checkpoint for checkpoint in checkpoints if checkpoint.frame_changed]), len(on_candidate_calls))

    def test_collect_checkpoints_default_debounce_keeps_only_spaced_candidates(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            workers=1,
            max_pending_ocr_frames=2,
        )
        fake_capture = self._FakeVideoCapture(list(range(19)))
        on_candidate_calls: list[tuple[int, object]] = []
        visually_similar_flags = [False] * 6

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{roi_frame}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return roi_frame

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return visually_similar_flags.pop(0)

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.0

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                                _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        self.assertEqual([index for index, _image in on_candidate_calls], [0, 2, 4, 6])

    def test_collect_checkpoints_entry_debounce_delays_first_distinct_candidate_in_changed_run(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            workers=1,
            max_pending_ocr_frames=2,
            ocr_entry_debounce_seconds=0.225,
        )
        fake_capture = self._FakeVideoCapture(list(range(19)))
        on_candidate_calls: list[tuple[int, object]] = []
        visually_similar_flags = [False] * 6

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{roi_frame}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return roi_frame

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return visually_similar_flags.pop(0)

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.0

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                                _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        self.assertEqual([index for index, _image in on_candidate_calls], [0, 3, 6])

    def test_collect_checkpoints_keeps_later_distinct_change_after_gap(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            workers=1,
            max_pending_ocr_frames=2,
        )
        fake_capture = self._FakeVideoCapture(list(range(19)))
        on_candidate_calls: list[tuple[int, object]] = []
        visually_similar_flags = [False, True, True, True, True, False]

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{roi_frame}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return roi_frame

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return visually_similar_flags.pop(0)

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.0

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                                checkpoints, stats = _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        call_indices = [index for index, _image in on_candidate_calls]
        self.assertEqual(stats.sampled_frames, 7)
        self.assertIn(0, call_indices)
        self.assertIn(6, call_indices)
        self.assertGreaterEqual(len(call_indices), 2)
        self.assertEqual(stats.submitted_ocr_frames, len(call_indices))
        self.assertEqual(len([checkpoint for checkpoint in checkpoints if checkpoint.frame_changed]), len(call_indices))

    def test_collect_checkpoints_reuses_prepared_sampled_frame_for_submitted_candidates(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=1,
            workers=1,
            max_pending_ocr_frames=2,
        )
        frame_a = object()
        frame_b = object()
        fake_capture = self._FakeVideoCapture([frame_a, frame_b])
        on_candidate_calls: list[tuple[int, object]] = []
        prepare_calls: list[object] = []

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{roi_frame}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            prepare_calls.append(roi_frame)
            return f"ocr-{len(prepare_calls)}"

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return False

        similarity_scores = iter([0.99])

        def fake_similarity_score(previous, current):
            del previous, current
            return next(similarity_scores)

        class FakeBackend:
            def recognize(self, image):
                return OCRText(text=str(image), score=1.0, lines=[str(image)])

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                                with patch("subx.pipeline.create_backend", return_value=FakeBackend()):
                                    checkpoints, stats = _collect_checkpoints(
                                        config,
                                        on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                        progress_reporter=None,
                                    )

        self.assertEqual(stats.sampled_frames, 2)
        self.assertEqual(stats.submitted_ocr_frames, 1)
        self.assertEqual(stats.reused_frames, 1)
        self.assertEqual(prepare_calls, [frame_a, frame_b])
        self.assertEqual(on_candidate_calls, [(0, "ocr-1")])
        self.assertEqual([checkpoint.frame_changed for checkpoint in checkpoints], [True, False])

    def test_collect_checkpoints_uses_grab_for_non_sampled_frames_and_retrieve_for_sampled_frames(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=2,
            workers=1,
            max_pending_ocr_frames=2,
        )
        fake_capture = self._GrabRetrieveVideoCapture(["frame-0", "frame-1", "frame-2", "frame-3", "frame-4"], fps=8.0)
        on_candidate_calls: list[tuple[int, object]] = []
        prepare_calls: list[object] = []

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            prepare_calls.append(roi_frame)
            return f"ocr-{roi_frame}"

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return False

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.0

        class FakeBackend:
            def recognize(self, image):
                return OCRText(text=str(image), score=1.0, lines=[str(image)])

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                    with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                        with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                            with patch("subx.pipeline.create_backend", return_value=FakeBackend()):
                                checkpoints, stats = _collect_checkpoints(
                                    config,
                                    on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                    progress_reporter=None,
                                )

        self.assertEqual(fake_capture.read_calls, 0)
        self.assertEqual(fake_capture.grab_calls, [0, 1, 2, 3, 4])
        self.assertEqual(fake_capture.retrieve_calls, [0, 2, 4])
        self.assertEqual(prepare_calls, ["frame-0", "frame-2", "frame-4"])
        self.assertEqual([index for index, _image in on_candidate_calls], [0, 1, 2])
        self.assertEqual([image for _index, image in on_candidate_calls], ["ocr-frame-0", "ocr-frame-2", "ocr-frame-4"])
        self.assertEqual(stats.sampled_frames, 3)
        self.assertEqual(stats.submitted_ocr_frames, 3)
        self.assertEqual(stats.reused_frames, 0)
        self.assertEqual([checkpoint.frame_changed for checkpoint in checkpoints], [True, True, True])
        self.assertEqual([checkpoint.time_seconds for checkpoint in checkpoints], [0.0, 0.25, 0.5])

    def test_collect_checkpoints_samples_final_frame_even_when_off_interval(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=1,
            max_pending_ocr_frames=2,
        )
        fake_capture = self._GrabRetrieveVideoCapture(["frame-0", "frame-1", "frame-2", "frame-3", "frame-4"], fps=10.0)
        on_candidate_calls: list[tuple[int, object]] = []

        def fake_crop_frame(frame, roi):
            del roi
            return frame

        def fake_prepare_roi_gray(roi_frame, resize_max_width):
            del resize_max_width
            return f"gray-{roi_frame}"

        def fake_resize_roi_frame(roi_frame, resize_max_width):
            del resize_max_width
            return f"ocr-{roi_frame}"

        def fake_visually_similar(previous, current, diff_threshold):
            del previous, current, diff_threshold
            return False

        def fake_similarity_score(previous, current):
            del previous, current
            return 0.0

        class FakeBackend:
            def recognize(self, image):
                return OCRText(text=str(image), score=1.0, lines=[str(image)])

        with patch("cv2.VideoCapture", return_value=fake_capture):
            with patch("subx.pipeline.crop_frame", side_effect=fake_crop_frame):
                with patch("subx.pipeline._prepare_roi_gray", side_effect=fake_prepare_roi_gray):
                    with patch("subx.pipeline._resize_roi_frame", side_effect=fake_resize_roi_frame):
                        with patch("subx.pipeline._is_visually_similar", side_effect=fake_visually_similar):
                            with patch("subx.pipeline._candidate_similarity_score", side_effect=fake_similarity_score, create=True):
                                with patch("subx.pipeline.create_backend", return_value=FakeBackend()):
                                    checkpoints, stats = _collect_checkpoints(
                                        config,
                                        on_candidate=lambda index, image: on_candidate_calls.append((index, image)),
                                        progress_reporter=None,
                                    )

        self.assertEqual(fake_capture.read_calls, 0)
        self.assertEqual(fake_capture.grab_calls, [0, 1, 2, 3, 4])
        self.assertEqual(fake_capture.retrieve_calls, [0, 3, 4])
        self.assertEqual([index for index, _image in on_candidate_calls], [0, 1])
        self.assertEqual([image for _index, image in on_candidate_calls], ["ocr-frame-0", "ocr-frame-3"])
        self.assertEqual(stats.sampled_frames, 3)
        self.assertEqual(stats.submitted_ocr_frames, 2)
        self.assertEqual(stats.reused_frames, 1)
        self.assertEqual([checkpoint.frame_changed for checkpoint in checkpoints], [True, True, False])
        self.assertEqual([checkpoint.time_seconds for checkpoint in checkpoints], [0.0, 0.3, 0.4])

    def test_extract_subtitles_does_not_emit_per_batch_ocr_progress(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            sample_every=3,
            workers=1,
            max_pending_ocr_frames=2,
        )

        def fake_collect(config_arg, on_candidate=None, progress_reporter=None):
            self.assertIsNotNone(on_candidate)
            self.assertIsNotNone(progress_reporter)
            for index in range(3):
                on_candidate(index, f"frame-{index}")
            checkpoints = [
                Checkpoint(index=index, time_seconds=float(index), frame_changed=True)
                for index in range(3)
            ]
            stats = PipelineStats(sampled_frames=3, submitted_ocr_frames=3)
            return checkpoints, stats

        class FakeBackend:
            def recognize(self, image):
                return OCRText(text=str(image), score=1.0, lines=[str(image)])

        stderr = io.StringIO()
        with patch("subx.pipeline._collect_checkpoints", side_effect=fake_collect):
            with patch("subx.pipeline.create_backend", return_value=FakeBackend()):
                with redirect_stderr(stderr):
                    extract_subtitles(config)

        self.assertNotIn("OCR (", stderr.getvalue())

    def test_extract_subtitles_rejects_negative_entry_debounce(self) -> None:
        config = ExtractConfig(
            video_path=Path("clip.mp4"),
            output_path=Path("clip.srt"),
            ocr_entry_debounce_seconds=-0.1,
        )

        with self.assertRaises(ValueError):
            extract_subtitles(config)

if __name__ == "__main__":
    unittest.main()
