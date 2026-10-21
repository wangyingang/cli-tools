from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ROI:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("ROI values must be within [0, 1].")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("ROI width and height must be greater than 0.")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("ROI must fit within the normalized frame.")

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.width, self.height]

    def crop_bounds(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        left = max(0, min(frame_width - 1, int(round(self.x * frame_width))))
        top = max(0, min(frame_height - 1, int(round(self.y * frame_height))))
        right = max(left + 1, min(frame_width, int(round((self.x + self.width) * frame_width))))
        bottom = max(top + 1, min(frame_height, int(round((self.y + self.height) * frame_height))))
        return left, top, right, bottom


@dataclass
class OCRText:
    text: str
    score: float = 0.0
    lines: list[str] = field(default_factory=list)


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


@dataclass
class PipelineStats:
    total_frames: int = 0
    sampled_frames: int = 0
    submitted_ocr_frames: int = 0
    reused_frames: int = 0
    produced_cues: int = 0
    elapsed_seconds: float = 0.0
    fps: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractResult:
    cues: list[SubtitleCue]
    stats: PipelineStats
    output_path: Path | None = None


@dataclass
class SampleMeta:
    lang: str = "mixed"
    roi: ROI | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class SampleCase:
    sample_id: str
    clip_path: Path
    truth_path: Path
    meta_path: Path
    meta: SampleMeta


@dataclass
class SampleEvaluation:
    sample_id: str
    engine: str
    lang: str
    roi: list[float]
    cer: float
    wer: float
    cue_exact_match: float
    overlap_hit_rate: float
    mean_start_error: float | None
    mean_end_error: float | None
    total_elapsed_seconds: float
    ocr_calls: int
    sampled_frames: int
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
