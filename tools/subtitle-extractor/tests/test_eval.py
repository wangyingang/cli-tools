import unittest

from subx.eval import _cue_metrics
from subx.types import SubtitleCue


class EvalTests(unittest.TestCase):
    def test_cue_metrics(self) -> None:
        predicted = [SubtitleCue(start=0.0, end=1.0, text="hello")]
        truth = [SubtitleCue(start=0.0, end=1.0, text="hello")]
        exact, overlap, mean_start, mean_end = _cue_metrics(predicted, truth)
        self.assertEqual(exact, 1.0)
        self.assertEqual(overlap, 1.0)
        self.assertEqual(mean_start, 0.0)
        self.assertEqual(mean_end, 0.0)


if __name__ == "__main__":
    unittest.main()
