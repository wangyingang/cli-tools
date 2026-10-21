import unittest
from pathlib import Path
from unittest.mock import patch

from subx.cli import (
    build_parser as build_subx_parser,
    resolve_ocr_candidate_similarity_threshold,
    resolve_ocr_entry_debounce_seconds,
    resolve_roi_args,
    resolve_sample_every,
)
from subx.dev_cli import build_parser as build_dev_parser


class CliTests(unittest.TestCase):
    def test_subx_parser_accepts_direct_video_argument(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4"])
        self.assertEqual(args.video, "clip.mp4")
        self.assertEqual(args.engine, "paddle")
        self.assertEqual(args.lines, "single")
        self.assertEqual(args.speed_profile, "balanced")
        self.assertIsNone(args.sample_every)
        self.assertEqual(args.workers, 6)

    def test_subx_parser_resolves_default_sample_every_from_lines_preset(self) -> None:
        single_args = build_subx_parser().parse_args(["clip.mp4"])
        double_args = build_subx_parser().parse_args(["clip.mp4", "-l", "double"])
        explicit_args = build_subx_parser().parse_args(["clip.mp4", "-l", "double", "--sample-every", "4"])
        self.assertEqual(resolve_sample_every(single_args), 6)
        self.assertEqual(resolve_sample_every(double_args), 6)
        self.assertEqual(resolve_sample_every(explicit_args), 4)

    def test_subx_parser_resolves_default_similarity_threshold_from_lines_preset(self) -> None:
        single_args = build_subx_parser().parse_args(["clip.mp4"])
        double_args = build_subx_parser().parse_args(["clip.mp4", "-l", "double"])
        self.assertEqual(resolve_ocr_candidate_similarity_threshold(single_args), 0.86)
        self.assertEqual(resolve_ocr_candidate_similarity_threshold(double_args), 0.8)

    def test_subx_parser_resolves_entry_debounce_from_speed_profile(self) -> None:
        balanced_single = build_subx_parser().parse_args(["clip.mp4"])
        aggressive_single = build_subx_parser().parse_args(["clip.mp4", "--speed-profile", "aggressive"])
        aggressive_double = build_subx_parser().parse_args(["clip.mp4", "-l", "double", "--speed-profile", "aggressive"])
        self.assertEqual(resolve_ocr_entry_debounce_seconds(balanced_single), 0.0)
        self.assertEqual(resolve_ocr_entry_debounce_seconds(aggressive_single), 0.225)
        self.assertEqual(resolve_ocr_entry_debounce_seconds(aggressive_double), 0.0)

    def test_subx_parser_resolves_single_line_roi_preset(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4", "-l", "single"])
        with patch("subx.cli._probe_video_frame_size", return_value=(1920, 1080)):
            roi = resolve_roi_args(args, video_path=Path("clip.mp4"))
        self.assertAlmostEqual(roi.x, 0.125)
        self.assertAlmostEqual(roi.y, 0.895)
        self.assertAlmostEqual(roi.width, 0.75)
        self.assertAlmostEqual(roi.height, 0.105)

    def test_subx_parser_resolves_double_line_roi_preset_to_full_width_default(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4", "-l", "double"])
        with patch("subx.cli._probe_video_frame_size", return_value=(1920, 1080)):
            roi = resolve_roi_args(args, video_path=Path("clip.mp4"))
        self.assertAlmostEqual(roi.x, 0.0)
        self.assertAlmostEqual(roi.y, 0.8)
        self.assertAlmostEqual(roi.width, 1.0)
        self.assertAlmostEqual(roi.height, 0.2)

    def test_subx_parser_resolves_double_line_roi_preset_with_narrow_width(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4", "-l", "double", "-w", "0.8"])
        with patch("subx.cli._probe_video_frame_size", return_value=(1920, 1080)):
            roi = resolve_roi_args(args, video_path=Path("clip.mp4"))
        self.assertAlmostEqual(roi.x, 0.1)
        self.assertAlmostEqual(roi.width, 0.8)
        self.assertAlmostEqual(roi.height, 0.16)
        self.assertAlmostEqual(roi.y, 0.84)

    def test_subx_parser_resolves_structured_roi_components(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4", "-w", "0.8", "-H", "0.18", "-b", "0.02"])
        roi = resolve_roi_args(args)
        self.assertAlmostEqual(roi.x, 0.1)
        self.assertAlmostEqual(roi.y, 0.8)
        self.assertAlmostEqual(roi.width, 0.8)
        self.assertAlmostEqual(roi.height, 0.18)

    def test_subx_parser_rejects_mixed_roi_syntaxes(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4", "--roi", "0,0.8,1,0.2", "-H", "0.18"])
        with self.assertRaises(ValueError):
            resolve_roi_args(args)

    def test_subx_help_describes_structured_roi_defaults(self) -> None:
        help_text = build_subx_parser().format_help()
        self.assertIn("--lines {single,double}", help_text)
        self.assertIn("default: single", help_text.lower())
        self.assertIn("Default: derived from --lines", help_text)
        self.assertIn("single=0.75, double=1.0", help_text)
        self.assertIn("preset and video size.", help_text)
        self.assertIn("Default: 0.0.", help_text)
        self.assertIn("OCR language preset.", help_text)
        self.assertIn("OCR backend.", help_text)
        self.assertIn("--speed-profile {balanced,aggressive}", help_text)
        self.assertIn("default: balanced", help_text.lower())
        self.assertIn("single=6, double=6", help_text)
        self.assertIn("default: 6", help_text.lower())

    def test_subx_parser_no_longer_accepts_eval_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            build_subx_parser().parse_args(["eval", "./samples"])

    def test_subx_dev_parser_accepts_eval_subcommand(self) -> None:
        args = build_dev_parser().parse_args(["eval", "./samples"])
        self.assertEqual(args.command, "eval")
        self.assertEqual(args.engine, "paddle")
        self.assertEqual(args.default_roi, "0,0.8,1,0.2")
        self.assertEqual(args.workers, 6)

    def test_subx_dev_parser_accepts_bench_subcommand(self) -> None:
        args = build_dev_parser().parse_args(["bench", "./samples"])
        self.assertEqual(args.command, "bench")
        self.assertEqual(args.engine, "paddle")
        self.assertEqual(args.default_roi, "0,0.8,1,0.2")
        self.assertEqual(args.workers, 6)


if __name__ == "__main__":
    unittest.main()
