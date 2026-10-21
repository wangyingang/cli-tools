import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from subx.srt import format_srt_timestamp, parse_srt, write_srt
from subx.types import SubtitleCue


class SrtTests(unittest.TestCase):
    def test_format_srt_timestamp(self) -> None:
        self.assertEqual(format_srt_timestamp(1.234), "00:00:01,234")

    def test_write_and_parse_srt(self) -> None:
        cues = [SubtitleCue(start=0.0, end=1.5, text="hello\nworld")]
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.srt"
            write_srt(cues, path)
            parsed = parse_srt(path)
            self.assertEqual(parsed, cues)


if __name__ == "__main__":
    unittest.main()
