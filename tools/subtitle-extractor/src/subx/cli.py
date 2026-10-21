from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import ExtractConfig, extract_subtitles
from .roi import DEFAULT_ROI, build_centered_bottom_roi, build_centered_bottom_roi_for_prepared_height, parse_roi
from .srt import write_srt

_LINE_PRESET_DEFAULT_WIDTHS = {
    "single": 0.75,
    "double": 1.0,
}
_LINE_PRESET_SAMPLE_EVERY = {
    "single": 6,
    "double": 6,
}
_LINE_PRESET_OCR_SIMILARITY_THRESHOLDS = {
    "single": 0.86,
    "double": 0.8,
}
_SPEED_PROFILE_SINGLE_ENTRY_DEBOUNCE_SECONDS = {
    "balanced": 0.0,
    "aggressive": 0.225,
}
_SINGLE_LINE_TARGET_PREPARED_HEIGHT = 100.8
_DOUBLE_LINE_TARGET_PREPARED_HEIGHT = 144.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subx",
        description="Extract hard subtitles from one video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("video", help="Path to the input video.")
    parser.add_argument("--output", help="Output .srt path. Defaults to <video>.srt.")
    parser.add_argument(
        "--roi",
        help="Explicit ROI as x,y,w,h in normalized coordinates. Default: disabled; when omitted, structured ROI parameters are used.",
    )
    parser.add_argument(
        "-l",
        "--lines",
        choices=["single", "double"],
        default="single",
        help="Expected subtitle line count for ROI-height preset selection.",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=float,
        help="Normalized ROI width. Structured ROI stays horizontally centered. Default: derived from --lines preset (single=0.75, double=1.0).",
    )
    parser.add_argument(
        "-H",
        "--height",
        type=float,
        help="Normalized ROI height. Default: derived from --lines preset and video size.",
    )
    parser.add_argument(
        "-b",
        "--bottom-offset",
        type=float,
        help="Normalized gap between ROI bottom edge and frame bottom edge. Default: 0.0.",
    )
    parser.add_argument("--lang", choices=["zh", "en", "mixed"], default="mixed", help="OCR language preset.")
    parser.add_argument("--engine", choices=["paddle", "onnx"], default="paddle", help="OCR backend.")
    parser.add_argument(
        "--speed-profile",
        choices=["balanced", "aggressive"],
        default="balanced",
        help="Performance/accuracy tradeoff preset. aggressive currently only affects single-line subtitle extraction.",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        help="Sample one frame every N frames before OCR candidate filtering. Default: derived from --lines preset (single=6, double=6).",
    )
    parser.add_argument("--workers", type=int, default=6, help="OCR worker process count.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    video_path = Path(args.video)
    output_path = Path(args.output) if args.output else video_path.with_suffix(".srt")
    try:
        roi = resolve_roi_args(args, video_path=video_path)
    except ValueError as exc:
        parser.error(str(exc))
    result = extract_subtitles(
        ExtractConfig(
            video_path=video_path,
            output_path=output_path,
            roi=roi,
            lang=args.lang,
            engine=args.engine,
            sample_every=resolve_sample_every(args),
            workers=args.workers,
            ocr_candidate_similarity_threshold=resolve_ocr_candidate_similarity_threshold(args),
            ocr_entry_debounce_seconds=resolve_ocr_entry_debounce_seconds(args),
        )
    )
    write_srt(result.cues, output_path)
    print(json.dumps({"output": str(output_path), "stats": result.stats.to_dict()}, ensure_ascii=False, indent=2))
    return 0


def resolve_roi_args(args: argparse.Namespace, video_path: Path | None = None):
    uses_structured_roi = any(value is not None for value in (args.width, args.height, args.bottom_offset)) or args.lines != "single"
    if args.roi is not None and uses_structured_roi:
        raise ValueError("--roi cannot be combined with --lines/--width/--height/--bottom-offset.")
    if args.roi is not None:
        return parse_roi(args.roi)

    width = args.width if args.width is not None else _LINE_PRESET_DEFAULT_WIDTHS[args.lines]
    if args.height is not None:
        height = args.height
        bottom_offset = args.bottom_offset if args.bottom_offset is not None else 0.0
        return build_centered_bottom_roi(width=width, height=height, bottom_offset=bottom_offset)

    if video_path is None:
        raise ValueError("video_path is required when ROI height depends on line presets.")
    frame_width, frame_height = _probe_video_frame_size(video_path)
    prepared_height_px = _SINGLE_LINE_TARGET_PREPARED_HEIGHT if args.lines == "single" else _DOUBLE_LINE_TARGET_PREPARED_HEIGHT
    bottom_offset = args.bottom_offset if args.bottom_offset is not None else 0.0
    return build_centered_bottom_roi_for_prepared_height(
        frame_width=frame_width,
        frame_height=frame_height,
        width=width,
        prepared_height_px=prepared_height_px,
        bottom_offset=bottom_offset,
    )


def _probe_video_frame_size(video_path: Path) -> tuple[int, int]:
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video for ROI sizing: {video_path}")
    try:
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError(f"Unable to read frame size from video: {video_path}")
    return frame_width, frame_height


def resolve_sample_every(args: argparse.Namespace) -> int:
    return args.sample_every if args.sample_every is not None else _LINE_PRESET_SAMPLE_EVERY[args.lines]


def resolve_ocr_candidate_similarity_threshold(args: argparse.Namespace) -> float:
    return _LINE_PRESET_OCR_SIMILARITY_THRESHOLDS[args.lines]


def resolve_ocr_entry_debounce_seconds(args: argparse.Namespace) -> float:
    if args.lines != "single":
        return 0.0
    return _SPEED_PROFILE_SINGLE_ENTRY_DEBOUNCE_SECONDS[args.speed_profile]


if __name__ == "__main__":
    sys.exit(main())
