from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .types import SubtitleCue


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    td = _dt.timedelta(milliseconds=milliseconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(cues: list[SubtitleCue], path: Path) -> None:
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_srt(path: Path) -> list[SubtitleCue]:
    blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timing_line = lines[1] if "-->" in lines[1] else lines[0]
        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        start_text, end_text = [part.strip() for part in timing_line.split("-->")]
        cues.append(
            SubtitleCue(
                start=parse_srt_timestamp(start_text),
                end=parse_srt_timestamp(end_text),
                text="\n".join(text_lines).strip(),
            )
        )
    return cues


def parse_srt_timestamp(value: str) -> float:
    hhmmss, millis = value.split(",")
    hours, minutes, seconds = [int(part) for part in hhmmss.split(":")]
    return hours * 3600 + minutes * 60 + seconds + int(millis) / 1000
