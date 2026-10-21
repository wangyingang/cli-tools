from __future__ import annotations

import json
from pathlib import Path

from .roi import DEFAULT_ROI, parse_roi
from .srt import parse_srt, write_srt
from .text import character_error_rate, normalize_text, word_error_rate
from .types import ROI, SampleCase, SampleEvaluation, SampleMeta, SubtitleCue


def load_samples(samples_dir: Path, default_roi: ROI) -> list[SampleCase]:
    cases: list[SampleCase] = []
    for entry in sorted(path for path in samples_dir.iterdir() if path.is_dir()):
        clip_path = entry / "clip.mp4"
        truth_path = entry / "truth.srt"
        meta_path = entry / "meta.json"
        if not clip_path.exists() or not truth_path.exists() or not meta_path.exists():
            continue
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        roi = parse_roi(",".join(str(part) for part in payload["roi"])) if "roi" in payload else default_roi
        meta = SampleMeta(lang=payload.get("lang", "mixed"), roi=roi, tags=payload.get("tags", []))
        cases.append(
            SampleCase(
                sample_id=entry.name,
                clip_path=clip_path,
                truth_path=truth_path,
                meta_path=meta_path,
                meta=meta,
            )
        )
    return cases


def evaluate_samples(
    samples_dir: Path,
    engines: list[str],
    default_roi: ROI,
    output_root: Path,
    sample_every: int,
    workers: int,
) -> list[SampleEvaluation]:
    from .pipeline import ExtractConfig, extract_subtitles

    cases = load_samples(samples_dir, default_roi)
    results: list[SampleEvaluation] = []
    for engine in engines:
        for case in cases:
            extract_output = output_root / engine / f"{case.sample_id}.srt"
            extract_output.parent.mkdir(parents=True, exist_ok=True)
            extract_result = extract_subtitles(
                ExtractConfig(
                    video_path=case.clip_path,
                    output_path=extract_output,
                    roi=case.meta.roi or default_roi,
                    lang=case.meta.lang,
                    engine=engine,
                    sample_every=sample_every,
                    workers=workers,
                )
            )
            write_srt(extract_result.cues, extract_output)
            truth_cues = parse_srt(case.truth_path)
            results.append(_score_case(case, engine, extract_result, truth_cues))
    return results


def benchmark_samples(
    samples_dir: Path,
    engines: list[str],
    default_roi: ROI,
    sample_every: int,
    workers: int,
) -> list[dict]:
    from .pipeline import ExtractConfig, extract_subtitles

    cases = load_samples(samples_dir, default_roi)
    reports: list[dict] = []
    for engine in engines:
        for case in cases:
            result = extract_subtitles(
                ExtractConfig(
                    video_path=case.clip_path,
                    output_path=case.clip_path.with_suffix(".bench.srt"),
                    roi=case.meta.roi or default_roi,
                    lang=case.meta.lang,
                    engine=engine,
                    sample_every=sample_every,
                    workers=workers,
                )
            )
            reports.append(
                {
                    "sample_id": case.sample_id,
                    "engine": engine,
                    "lang": case.meta.lang,
                    "roi": (case.meta.roi or default_roi).to_list(),
                    "elapsed_seconds": result.stats.elapsed_seconds,
                    "ocr_calls": result.stats.submitted_ocr_frames,
                    "sampled_frames": result.stats.sampled_frames,
                    "cues": len(result.cues),
                    "tags": case.meta.tags,
                }
            )
    return reports


def write_markdown_report(results: list[SampleEvaluation], path: Path) -> None:
    lines = [
        "# subx Evaluation Report",
        "",
        "| sample | engine | lang | CER | WER | cue exact | overlap hit | elapsed(s) | OCR calls | tags |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        tags = ", ".join(result.tags)
        lines.append(
            f"| {result.sample_id} | {result.engine} | {result.lang} | "
            f"{result.cer:.4f} | {result.wer:.4f} | {result.cue_exact_match:.4f} | "
            f"{result.overlap_hit_rate:.4f} | {result.total_elapsed_seconds:.2f} | "
            f"{result.ocr_calls} | {tags} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json_report(payload: list[dict], path: Path) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _score_case(case: SampleCase, engine: str, extract_result, truth_cues: list[SubtitleCue]) -> SampleEvaluation:
    predicted_text = "\n".join(cue.text for cue in extract_result.cues)
    truth_text = "\n".join(cue.text for cue in truth_cues)
    cue_exact, overlap_hit, mean_start_error, mean_end_error = _cue_metrics(extract_result.cues, truth_cues)
    return SampleEvaluation(
        sample_id=case.sample_id,
        engine=engine,
        lang=case.meta.lang,
        roi=(case.meta.roi or DEFAULT_ROI).to_list(),
        cer=character_error_rate(predicted_text, truth_text),
        wer=word_error_rate(predicted_text, truth_text),
        cue_exact_match=cue_exact,
        overlap_hit_rate=overlap_hit,
        mean_start_error=mean_start_error,
        mean_end_error=mean_end_error,
        total_elapsed_seconds=extract_result.stats.elapsed_seconds,
        ocr_calls=extract_result.stats.submitted_ocr_frames,
        sampled_frames=extract_result.stats.sampled_frames,
        tags=case.meta.tags,
    )


def _cue_metrics(predicted: list[SubtitleCue], truth: list[SubtitleCue]) -> tuple[float, float, float | None, float | None]:
    if not truth:
        return 0.0, 0.0, None, None

    exact_matches = 0
    overlap_hits = 0
    start_errors: list[float] = []
    end_errors: list[float] = []

    for truth_cue in truth:
        best = _best_overlap_match(truth_cue, predicted)
        if best is None:
            continue
        pred_cue, overlap_ratio = best
        if overlap_ratio >= 0.5:
            overlap_hits += 1
        if normalize_text(pred_cue.text) == normalize_text(truth_cue.text) and overlap_ratio > 0:
            exact_matches += 1
        if overlap_ratio > 0:
            start_errors.append(abs(pred_cue.start - truth_cue.start))
            end_errors.append(abs(pred_cue.end - truth_cue.end))

    exact_rate = exact_matches / len(truth)
    overlap_rate = overlap_hits / len(truth)
    mean_start = sum(start_errors) / len(start_errors) if start_errors else None
    mean_end = sum(end_errors) / len(end_errors) if end_errors else None
    return exact_rate, overlap_rate, mean_start, mean_end


def _best_overlap_match(truth_cue: SubtitleCue, predicted: list[SubtitleCue]) -> tuple[SubtitleCue, float] | None:
    best_match: tuple[SubtitleCue, float] | None = None
    for pred_cue in predicted:
        overlap_start = max(truth_cue.start, pred_cue.start)
        overlap_end = min(truth_cue.end, pred_cue.end)
        overlap = max(0.0, overlap_end - overlap_start)
        if overlap <= 0:
            continue
        union = max(truth_cue.end, pred_cue.end) - min(truth_cue.start, pred_cue.start)
        ratio = overlap / union if union else 0.0
        if best_match is None or ratio > best_match[1]:
            best_match = (pred_cue, ratio)
    return best_match
