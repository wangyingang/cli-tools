import unittest

from subx.cli import build_parser as build_subx_parser
from subx.dev_cli import build_parser as build_dev_parser


class CliTests(unittest.TestCase):
    def test_subx_parser_accepts_direct_video_argument(self) -> None:
        args = build_subx_parser().parse_args(["clip.mp4"])
        self.assertEqual(args.video, "clip.mp4")
        self.assertEqual(args.engine, "paddle")

    def test_subx_parser_no_longer_accepts_eval_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            build_subx_parser().parse_args(["eval", "./samples"])

    def test_subx_dev_parser_accepts_eval_subcommand(self) -> None:
        args = build_dev_parser().parse_args(["eval", "./samples"])
        self.assertEqual(args.command, "eval")
        self.assertEqual(args.engine, "paddle")

    def test_subx_dev_parser_accepts_bench_subcommand(self) -> None:
        args = build_dev_parser().parse_args(["bench", "./samples"])
        self.assertEqual(args.command, "bench")
        self.assertEqual(args.engine, "paddle")


if __name__ == "__main__":
    unittest.main()
