from __future__ import annotations

from .types import ROI


DEFAULT_ROI = ROI(0.0, 0.8, 1.0, 0.2)


def parse_roi(value: str | None) -> ROI:
    if value is None:
        return DEFAULT_ROI
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI must be provided as x,y,w,h.")
    try:
        x, y, width, height = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("ROI values must be numeric.") from exc
    return ROI(x=x, y=y, width=width, height=height)


def build_centered_bottom_roi(width: float, height: float, bottom_offset: float = 0.0) -> ROI:
    x = (1.0 - width) / 2.0
    y = 1.0 - bottom_offset - height
    return ROI(x=x, y=y, width=width, height=height)


def build_centered_bottom_roi_for_prepared_height(
    *,
    frame_width: int,
    frame_height: int,
    width: float,
    prepared_height_px: float,
    bottom_offset: float = 0.0,
    resize_max_width: int = 1280,
) -> ROI:
    cropped_width_px = frame_width * width
    scale = 1.0
    if cropped_width_px > resize_max_width:
        scale = resize_max_width / cropped_width_px
    height = prepared_height_px / max(frame_height * scale, 1.0)
    return build_centered_bottom_roi(width=width, height=height, bottom_offset=bottom_offset)


def crop_frame(frame, roi: ROI):
    frame_height, frame_width = frame.shape[:2]
    left, top, right, bottom = roi.crop_bounds(frame_width, frame_height)
    return frame[top:bottom, left:right]
