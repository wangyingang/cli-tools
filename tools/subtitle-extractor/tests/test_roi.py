import unittest

from subx.roi import DEFAULT_ROI, parse_roi


class RoiTests(unittest.TestCase):
    def test_parse_roi_defaults(self) -> None:
        roi = parse_roi(None)
        self.assertEqual(roi, DEFAULT_ROI)

    def test_parse_roi_values(self) -> None:
        roi = parse_roi("0.1,0.2,0.7,0.3")
        self.assertEqual(roi.to_list(), [0.1, 0.2, 0.7, 0.3])


if __name__ == "__main__":
    unittest.main()
