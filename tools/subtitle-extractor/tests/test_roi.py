import unittest

from subx.roi import (
    DEFAULT_ROI,
    build_centered_bottom_roi,
    build_centered_bottom_roi_for_prepared_height,
    parse_roi,
)


class RoiTests(unittest.TestCase):
    def test_parse_roi_defaults(self) -> None:
        roi = parse_roi(None)
        self.assertEqual(roi, DEFAULT_ROI)
        self.assertEqual(roi.to_list(), [0.0, 0.8, 1.0, 0.2])

    def test_parse_roi_values(self) -> None:
        roi = parse_roi("0.1,0.2,0.7,0.3")
        self.assertEqual(roi.to_list(), [0.1, 0.2, 0.7, 0.3])

    def test_build_centered_bottom_roi(self) -> None:
        roi = build_centered_bottom_roi(width=0.8, height=0.18, bottom_offset=0.02)
        self.assertAlmostEqual(roi.x, 0.1)
        self.assertAlmostEqual(roi.y, 0.8)
        self.assertAlmostEqual(roi.width, 0.8)
        self.assertAlmostEqual(roi.height, 0.18)

    def test_build_centered_bottom_roi_for_prepared_height(self) -> None:
        roi = build_centered_bottom_roi_for_prepared_height(
            frame_width=1920,
            frame_height=1080,
            width=1.0,
            prepared_height_px=100.8,
            bottom_offset=0.0,
        )
        self.assertAlmostEqual(roi.x, 0.0)
        self.assertAlmostEqual(roi.y, 0.86)
        self.assertAlmostEqual(roi.width, 1.0)
        self.assertAlmostEqual(roi.height, 0.14)


if __name__ == "__main__":
    unittest.main()
