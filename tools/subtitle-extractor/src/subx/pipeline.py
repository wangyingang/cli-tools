from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .ocr import create_backend
from .roi import DEFAULT_ROI, crop_frame
from .text import normalize_text, text_similarity
from .types import ExtractResult, OCRText, PipelineStats, ROI, SubtitleCue

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class ExtractConfig:
    video_path: Path
    output_path: Path
    roi: ROI = DEFAULT_ROI
    lang: str = "mixed"
    engine: str = "paddle"
    sample_every: int = 3
    workers: int = 6
    diff_threshold: float = 0.01
    ocr_candidate_similarity_threshold: float = 0.86
    ocr_entry_debounce_seconds: float = 0.0
    ocr_min_score: float = 0.5
    resize_max_width: int = 1280
    max_pending_ocr_frames: int = 64


@dataclass(frozen=True)
class Checkpoint:
    index: int
    time_seconds: float
    frame_changed: bool
    image: "np.ndarray | None" = None


_WORKER_BACKEND = None
_WORKER_PROCESS_POOL = None
_OCR_SUBMISSION_DEBOUNCE_SECONDS = 0.225


class ProgressReporter(Protocol):
    def update(self, amount: int = 1) -> None: ...
    def close(self) -> None: ...


class _OverallProgressReporter:
    def __init__(self, sample_every: int) -> None:
        self.sample_every = sample_every
        self.total_frames = 0
        self.processed_frames = 0
        self.queued_ocr = 0
        self.completed_ocr = 0
        self._progress = None

    def start(self, total_frames: int) -> None:
        from tqdm import tqdm

        self.total_frames = total_frames
        self._progress = tqdm(
            total=total_frames,
            unit="step",
            mininterval=0.5,
            desc="Extracting",
        )
        self._refresh()

    def advance_frame(self, amount: int = 1) -> None:
        self.processed_frames += amount
        if self._progress is not None:
            self._progress.update(amount)
            self._refresh()

    def queue_ocr(self, amount: int = 1) -> None:
        self.queued_ocr += amount
        if self._progress is not None:
            self._progress.total += amount
        self._refresh()

    def advance_ocr(self, amount: int = 1) -> None:
        self.completed_ocr += amount
        if self._progress is not None:
            self._progress.update(amount)
            self._refresh()

    def finish_sampling(self) -> None:
        if self._progress is None:
            return
        self._refresh()
        self._progress.refresh()

    def update(self, amount: int = 1) -> None:
        self.advance_ocr(amount)

    def close(self) -> None:
        if self._progress is not None:
            self._progress.close()

    def _refresh(self) -> None:
        if self._progress is None:
            return
        phase = "sampling" if self.processed_frames < self.total_frames else "ocr"
        self._progress.set_postfix_str(
            f"{phase} | frames {self.processed_frames}/{self.total_frames} | "
            f"ocr {self.completed_ocr}/{self.queued_ocr}",
            refresh=False,
        )


def extract_subtitles(
    config: ExtractConfig,
    progress_reporter: ProgressReporter | None = None,
) -> ExtractResult:
    if config.sample_every <= 0:
        raise ValueError("--sample-every must be greater than 0.")
    if config.workers <= 0:
        raise ValueError("--workers must be greater than 0.")
    if config.max_pending_ocr_frames <= 0:
        raise ValueError("--max-pending-ocr-frames must be greater than 0.")
    if config.ocr_entry_debounce_seconds < 0:
        raise ValueError("--ocr-entry-debounce-seconds must be greater than or equal to 0.")

    progress_reporter = progress_reporter or _OverallProgressReporter(sample_every=config.sample_every)
    started_at = time.perf_counter()
    pending_candidates: list[tuple[int, "np.ndarray"]] = []
    ocr_results: dict[int, OCRText] = {}
    single_worker_backend = None

    def get_single_worker_backend():
        nonlocal single_worker_backend
        if config.workers != 1:
            return None
        if single_worker_backend is None:
            single_worker_backend = create_backend(engine=config.engine, lang=config.lang)
        return single_worker_backend

    def on_candidate(index: int, image: "np.ndarray") -> None:
        pending_candidates.append((index, image))
        _queue_ocr_progress(progress_reporter)
        if len(pending_candidates) >= config.max_pending_ocr_frames:
            results = _run_ocr_candidates(
                pending_candidates,
                config,
                backend=get_single_worker_backend(),
            )
            ocr_results.update(results)
            _advance_ocr_progress(progress_reporter, len(results))
            pending_candidates.clear()

    try:
        checkpoints, stats = _collect_checkpoints(
            config,
            on_candidate=on_candidate,
            progress_reporter=progress_reporter,
        )
        _finish_sampling_progress(progress_reporter)
        if pending_candidates:
            results = _run_ocr_candidates(
                pending_candidates,
                config,
                backend=get_single_worker_backend(),
            )
            ocr_results.update(results)
            _advance_ocr_progress(progress_reporter, len(results))
        cues = _build_cues(checkpoints, ocr_results, config.ocr_min_score)
        stats.produced_cues = len(cues)
        stats.elapsed_seconds = time.perf_counter() - started_at
        return ExtractResult(cues=cues, stats=stats, output_path=config.output_path)
    finally:
        _shutdown_process_pool_executor()
        progress_reporter.close()


def _collect_checkpoints(
    config: ExtractConfig,
    on_candidate=None,
    progress_reporter: ProgressReporter | None = None,
) -> tuple[list[Checkpoint], PipelineStats]:
    import cv2

    capture = cv2.VideoCapture(str(config.video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video: {config.video_path}")

    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    stats = PipelineStats(total_frames=total_frames, fps=fps)
    _start_progress(progress_reporter, total_frames)

    checkpoints: list[Checkpoint] = []
    last_gray = None
    last_submitted_gray = None
    last_submitted_time = None
    pending_entry_time = None
    sample_index = 0
    frame_index = 0

    try:
        while True:
            if not capture.grab():
                break

            should_sample = frame_index % config.sample_every == 0 or frame_index == total_frames - 1
            if should_sample:
                ret, frame = capture.retrieve()
                if not ret:
                    break
                timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                stats.sampled_frames += 1
                roi_frame = crop_frame(frame, config.roi)
                prepared_roi_frame = _resize_roi_frame(roi_frame, config.resize_max_width)
                gray = _prepare_roi_gray(prepared_roi_frame, config.resize_max_width)
                changed = sample_index == 0 or not _is_visually_similar(last_gray, gray, config.diff_threshold)
                distinct_vs_last_submitted = changed and (
                    last_submitted_gray is None
                    or _candidate_similarity_score(last_submitted_gray, gray) < config.ocr_candidate_similarity_threshold
                )
                should_submit = distinct_vs_last_submitted
                if should_submit and config.sample_every > 1 and last_submitted_time is not None:
                    if config.ocr_entry_debounce_seconds > 0:
                        if pending_entry_time is None:
                            pending_entry_time = timestamp
                            should_submit = False
                        elif (timestamp - pending_entry_time) < config.ocr_entry_debounce_seconds:
                            should_submit = False
                        else:
                            should_submit = (timestamp - last_submitted_time) >= _OCR_SUBMISSION_DEBOUNCE_SECONDS
                    else:
                        should_submit = (timestamp - last_submitted_time) >= _OCR_SUBMISSION_DEBOUNCE_SECONDS
                checkpoints.append(
                    Checkpoint(
                        index=sample_index,
                        time_seconds=timestamp,
                        frame_changed=should_submit,
                        image=None,
                    )
                )
                if should_submit:
                    stats.submitted_ocr_frames += 1
                    if on_candidate is None:
                        raise RuntimeError("Changed frame candidate callback was not provided.")
                    on_candidate(sample_index, prepared_roi_frame)
                    last_submitted_gray = gray
                    last_submitted_time = timestamp
                    pending_entry_time = None
                else:
                    stats.reused_frames += 1
                    if not changed or not distinct_vs_last_submitted:
                        pending_entry_time = None
                sample_index += 1
                last_gray = gray

            frame_index += 1
            _advance_frame_progress(progress_reporter)
    finally:
        capture.release()
    return checkpoints, stats


def _resize_roi_frame(roi_frame: "np.ndarray | object", resize_max_width: int):
    import cv2

    if not hasattr(roi_frame, "shape"):
        return roi_frame

    if roi_frame.size == 0:
        raise RuntimeError("Computed ROI is empty. Check --roi values.")

    height, width = roi_frame.shape[:2]
    if width > resize_max_width:
        scale = resize_max_width / width
        roi_frame = cv2.resize(roi_frame, (resize_max_width, max(1, int(round(height * scale)))))
    return roi_frame


def _prepare_roi_gray(roi_frame: "np.ndarray | object", resize_max_width: int):
    import cv2

    del resize_max_width
    if not hasattr(roi_frame, "shape"):
        return roi_frame
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _is_visually_similar(previous: "np.ndarray | None", current: "np.ndarray", diff_threshold: float) -> bool:
    import cv2

    if previous is None or previous.shape != current.shape:
        return False
    diff = cv2.absdiff(previous, current)
    _, thresholded = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
    changed_pixels = cv2.countNonZero(thresholded)
    total_pixels = current.shape[0] * current.shape[1]
    change_ratio = changed_pixels / max(total_pixels, 1)
    return change_ratio < diff_threshold


def _candidate_similarity_score(previous: "np.ndarray | None", current: "np.ndarray") -> float:
    import cv2

    previous_shape = getattr(previous, "shape", None)
    current_shape = getattr(current, "shape", None)
    if previous is None or current is None:
        return 0.0
    if previous_shape is None or current_shape is None:
        return 1.0 if previous == current else 0.0
    if previous_shape != current_shape:
        return 0.0
    diff = cv2.absdiff(previous, current)
    _, thresholded = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
    changed_pixels = cv2.countNonZero(thresholded)
    total_pixels = current.shape[0] * current.shape[1]
    change_ratio = changed_pixels / max(total_pixels, 1)
    return max(0.0, 1.0 - change_ratio)


def _init_worker(engine: str, lang: str) -> None:
    global _WORKER_BACKEND
    _WORKER_BACKEND = create_backend(engine=engine, lang=lang)


def _run_ocr_candidates(
    candidates: list[tuple[int, "np.ndarray"]],
    config: ExtractConfig,
    backend=None,
) -> dict[int, OCRText]:
    if not candidates:
        return {}

    if config.workers == 1:
        if backend is None:
            backend = create_backend(engine=config.engine, lang=config.lang)
        results: dict[int, OCRText] = {}
        for index, image in _iter_ocr_candidates(candidates, config.engine):
            results[index] = backend.recognize(image)
        return results

    executor = _get_process_pool_executor(config)
    results = executor.map(_recognize_candidate, candidates)
    return {index: result for index, result in _iter_ocr_candidates(results, config.engine, total=len(candidates))}


def _recognize_candidate(item: tuple[int, "np.ndarray"]) -> tuple[int, OCRText]:
    index, image = item
    if _WORKER_BACKEND is None:
        raise RuntimeError("OCR worker backend was not initialized.")
    return index, _WORKER_BACKEND.recognize(image)


def _iter_ocr_candidates(items, engine: str, total: int | None = None):
    del engine, total
    yield from items


def _get_process_pool_executor(config: ExtractConfig):
    global _WORKER_PROCESS_POOL
    if _WORKER_PROCESS_POOL is None:
        _WORKER_PROCESS_POOL = ProcessPoolExecutor(
            max_workers=config.workers,
            initializer=_init_worker,
            initargs=(config.engine, config.lang),
        )
    return _WORKER_PROCESS_POOL


def _shutdown_process_pool_executor() -> None:
    global _WORKER_PROCESS_POOL
    if _WORKER_PROCESS_POOL is not None:
        _WORKER_PROCESS_POOL.shutdown(wait=True)
        _WORKER_PROCESS_POOL = None


def _start_progress(progress_reporter: ProgressReporter | None, total_frames: int) -> None:
    if progress_reporter is None:
        return
    start = getattr(progress_reporter, "start", None)
    if callable(start):
        start(total_frames)


def _advance_frame_progress(progress_reporter: ProgressReporter | None, amount: int = 1) -> None:
    if progress_reporter is None:
        return
    advance_frame = getattr(progress_reporter, "advance_frame", None)
    if callable(advance_frame):
        advance_frame(amount)
        return
    progress_reporter.update(amount)


def _queue_ocr_progress(progress_reporter: ProgressReporter | None, amount: int = 1) -> None:
    if progress_reporter is None:
        return
    queue_ocr = getattr(progress_reporter, "queue_ocr", None)
    if callable(queue_ocr):
        queue_ocr(amount)


def _advance_ocr_progress(progress_reporter: ProgressReporter | None, amount: int = 1) -> None:
    if progress_reporter is None:
        return
    advance_ocr = getattr(progress_reporter, "advance_ocr", None)
    if callable(advance_ocr):
        advance_ocr(amount)
        return
    for _ in range(amount):
        progress_reporter.update(1)


def _finish_sampling_progress(progress_reporter: ProgressReporter | None) -> None:
    if progress_reporter is None:
        return
    finish_sampling = getattr(progress_reporter, "finish_sampling", None)
    if callable(finish_sampling):
        finish_sampling()


def _build_cues(checkpoints: list[Checkpoint], ocr_results: dict[int, OCRText], min_score: float) -> list[SubtitleCue]:
    current_cue: SubtitleCue | None = None
    final_cues: list[SubtitleCue] = []
    last_text = ""
    last_time = checkpoints[0].time_seconds if checkpoints else 0.0

    for checkpoint in checkpoints:
        current_time = checkpoint.time_seconds
        if checkpoint.frame_changed:
            recognized = ocr_results.get(checkpoint.index)
            if recognized is None:
                current_text = last_text
            else:
                current_text = recognized.text if recognized.score >= min_score else ""
        else:
            current_text = last_text

        if text_similarity(last_text, current_text) >= 0.85:
            if current_cue and current_text:
                current_cue.end = current_time
        else:
            midpoint = last_time + ((current_time - last_time) / 2)
            if current_cue:
                if current_text:
                    current_cue.end = midpoint
                    final_cues.append(current_cue)
                    current_cue = SubtitleCue(start=midpoint, end=current_time, text=current_text)
                else:
                    current_cue.end = current_time
                    final_cues.append(current_cue)
                    current_cue = None
            elif current_text:
                current_cue = SubtitleCue(start=max(0.0, last_time), end=current_time, text=current_text)

        last_text = normalize_text(current_text)
        last_time = current_time

    if current_cue:
        final_cues.append(current_cue)

    return _merge_adjacent_cues(final_cues)


def _merge_adjacent_cues(cues: list[SubtitleCue]) -> list[SubtitleCue]:
    if not cues:
        return []
    merged = [cues[0]]
    for cue in cues[1:]:
        previous = merged[-1]
        if text_similarity(previous.text, cue.text) >= 0.9 and cue.start - previous.end < 1.0:
            previous.end = max(previous.end, cue.end)
        else:
            merged.append(cue)
    return [cue for cue in merged if cue.text]
