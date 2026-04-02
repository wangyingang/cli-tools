from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .eval import benchmark_samples, evaluate_samples, write_json_report, write_markdown_report
from .roi import parse_roi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subx-dev",
        description="Repository-only evaluation and benchmarking commands for subx.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("eval", help="Run OCR and compare against truth subtitles.")
    eval_parser.add_argument("samples_dir")
    eval_parser.add_argument("--engine", choices=["paddle", "onnx", "all"], default="paddle")
    eval_parser.add_argument("--default-roi", default="0,0.8,1,0.2")
    eval_parser.add_argument("--sample-every", type=int, default=3)
    eval_parser.add_argument("--workers", type=int, default=4)
    eval_parser.add_argument("--report")
    eval_parser.add_argument("--json")
    eval_parser.set_defaults(handler=_handle_eval)

    bench = subparsers.add_parser("bench", help="Benchmark OCR throughput without accuracy scoring.")
    bench.add_argument("samples_dir")
    bench.add_argument("--engine", choices=["paddle", "onnx", "all"], default="paddle")
    bench.add_argument("--default-roi", default="0,0.8,1,0.2")
    bench.add_argument("--sample-every", type=int, default=3)
    bench.add_argument("--workers", type=int, default=4)
    bench.add_argument("--json")
    bench.set_defaults(handler=_handle_bench)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


def _handle_eval(args: argparse.Namespace) -> int:
    samples_dir = Path(args.samples_dir)
    default_roi = parse_roi(args.default_roi)
    output_root = samples_dir / "_predictions"
    engines = _resolve_engines(args.engine)
    results = evaluate_samples(
        samples_dir=samples_dir,
        engines=engines,
        default_roi=default_roi,
        output_root=output_root,
        sample_every=args.sample_every,
        workers=args.workers,
    )
    if args.report:
        write_markdown_report(results, Path(args.report))
    if args.json:
        write_json_report([result.to_dict() for result in results], Path(args.json))
    print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
    return 0


def _handle_bench(args: argparse.Namespace) -> int:
    reports = benchmark_samples(
        samples_dir=Path(args.samples_dir),
        engines=_resolve_engines(args.engine),
        default_roi=parse_roi(args.default_roi),
        sample_every=args.sample_every,
        workers=args.workers,
    )
    if args.json:
        write_json_report(reports, Path(args.json))
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


def _resolve_engines(engine: str) -> list[str]:
    return ["paddle", "onnx"] if engine == "all" else [engine]


if __name__ == "__main__":
    sys.exit(main())
