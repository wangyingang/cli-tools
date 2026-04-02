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


def crop_frame(frame, roi: ROI):
    frame_height, frame_width = frame.shape[:2]
    left, top, right, bottom = roi.crop_bounds(frame_width, frame_height)
    return frame[top:bottom, left:right]
