from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import ExtractConfig, extract_subtitles
from .roi import parse_roi
from .srt import write_srt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subx", description="Extract hard subtitles from one video.")
    parser.add_argument("video", help="Path to the input video.")
    parser.add_argument("--output", help="Output .srt path. Defaults to <video>.srt.")
    parser.add_argument("--roi", default="0,0.8,1,0.2")
    parser.add_argument("--lang", choices=["zh", "en", "mixed"], default="mixed")
    parser.add_argument("--engine", choices=["paddle", "onnx"], default="paddle")
    parser.add_argument("--sample-every", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    video_path = Path(args.video)
    output_path = Path(args.output) if args.output else video_path.with_suffix(".srt")
    result = extract_subtitles(
        ExtractConfig(
            video_path=video_path,
            output_path=output_path,
            roi=parse_roi(args.roi),
            lang=args.lang,
            engine=args.engine,
            sample_every=args.sample_every,
            workers=args.workers,
        )
    )
    write_srt(result.cues, output_path)
    print(json.dumps({"output": str(output_path), "stats": result.stats.to_dict()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
