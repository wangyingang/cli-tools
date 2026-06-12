use std::path::Path;

use anyhow::{Context, Result, anyhow, bail};

#[derive(Clone, Copy, Debug)]
pub enum SubtitleFormat {
    Srt,
    Vtt,
    Ass,
    Ssa,
}

impl SubtitleFormat {
    pub fn from_path(path: &Path) -> Result<Self> {
        match path
            .extension()
            .and_then(|value| value.to_str())
            .map(|value| value.to_ascii_lowercase())
            .as_deref()
        {
            Some("srt") => Ok(Self::Srt),
            Some("vtt") => Ok(Self::Vtt),
            Some("ass") => Ok(Self::Ass),
            Some("ssa") => Ok(Self::Ssa),
            _ => bail!(
                "unsupported subtitle format for {}; expected .srt, .vtt, .ass, or .ssa",
                path.display()
            ),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Srt => "srt",
            Self::Vtt => "vtt",
            Self::Ass => "ass",
            Self::Ssa => "ssa",
        }
    }
}

pub fn trim_subtitle(
    source: &str,
    format: SubtitleFormat,
    clip_start_ms: u64,
    clip_end_ms: Option<u64>,
) -> Result<String> {
    match format {
        SubtitleFormat::Srt => trim_srt(source, clip_start_ms, clip_end_ms),
        SubtitleFormat::Vtt => trim_vtt(source, clip_start_ms, clip_end_ms),
        SubtitleFormat::Ass | SubtitleFormat::Ssa => trim_ass(source, clip_start_ms, clip_end_ms),
    }
}

fn trim_srt(source: &str, clip_start_ms: u64, clip_end_ms: Option<u64>) -> Result<String> {
    let normalized = normalize_newlines(source);
    let mut output = Vec::new();
    let mut cue_number = 1;
    let mut timing_lines = 0;

    for block in normalized.split("\n\n") {
        let lines: Vec<_> = block.lines().collect();
        let Some(index) = lines.iter().position(|line| line.contains("-->")) else {
            continue;
        };
        timing_lines += 1;
        let timing = parse_arrow_line(lines[index], parse_srt_timestamp)?;
        if let Some((start, end)) =
            clip_interval(timing.start, timing.end, clip_start_ms, clip_end_ms)
        {
            let mut rendered = vec![cue_number.to_string()];
            rendered.push(format!(
                "{} --> {}{}",
                format_srt_timestamp(start),
                format_srt_timestamp(end),
                timing.suffix
            ));
            rendered.extend(lines[index + 1..].iter().map(|line| (*line).to_string()));
            output.push(rendered.join("\n"));
            cue_number += 1;
        }
    }
    if timing_lines == 0 && !normalized.trim().is_empty() {
        bail!("subtitle contains no valid SRT timing lines");
    }
    Ok(if output.is_empty() {
        String::new()
    } else {
        format!("{}\n", output.join("\n\n"))
    })
}

fn trim_vtt(source: &str, clip_start_ms: u64, clip_end_ms: Option<u64>) -> Result<String> {
    let normalized = normalize_newlines(source);
    let mut blocks = normalized.split("\n\n");
    let header = blocks.next().unwrap_or("WEBVTT");
    if !header.trim_start_matches('\u{feff}').starts_with("WEBVTT") {
        bail!("VTT subtitle must start with WEBVTT");
    }
    let mut output = vec![header.to_string()];

    for block in blocks {
        let lines: Vec<_> = block.lines().collect();
        if let Some(index) = lines.iter().position(|line| line.contains("-->")) {
            let timing = parse_arrow_line(lines[index], parse_vtt_timestamp)?;
            if let Some((start, end)) =
                clip_interval(timing.start, timing.end, clip_start_ms, clip_end_ms)
            {
                let mut rendered: Vec<String> = lines[..index]
                    .iter()
                    .map(|line| (*line).to_string())
                    .collect();
                rendered.push(format!(
                    "{} --> {}{}",
                    format_vtt_timestamp(start),
                    format_vtt_timestamp(end),
                    timing.suffix
                ));
                rendered.extend(lines[index + 1..].iter().map(|line| (*line).to_string()));
                output.push(rendered.join("\n"));
            }
        } else if !block.trim().is_empty() {
            output.push(block.to_string());
        }
    }
    Ok(format!("{}\n", output.join("\n\n")))
}

fn trim_ass(source: &str, clip_start_ms: u64, clip_end_ms: Option<u64>) -> Result<String> {
    let normalized = normalize_newlines(source);
    let mut output = Vec::new();
    for line in normalized.lines() {
        let trimmed = line.trim_start();
        let Some(rest) = trimmed.strip_prefix("Dialogue:") else {
            output.push(line.to_string());
            continue;
        };
        let leading = &line[..line.len() - trimmed.len()];
        let mut fields: Vec<String> = rest
            .trim_start()
            .splitn(10, ',')
            .map(ToString::to_string)
            .collect();
        if fields.len() < 4 {
            bail!("invalid ASS/SSA Dialogue line: {line}");
        }
        let start = parse_ass_timestamp(&fields[1])?;
        let end = parse_ass_timestamp(&fields[2])?;
        if let Some((start, end)) = clip_interval(start, end, clip_start_ms, clip_end_ms) {
            fields[1] = format_ass_timestamp(start);
            fields[2] = format_ass_timestamp(end);
            output.push(format!("{leading}Dialogue: {}", fields.join(",")));
        }
    }
    Ok(format!("{}\n", output.join("\n")))
}

struct ArrowTiming {
    start: u64,
    end: u64,
    suffix: String,
}

fn parse_arrow_line(line: &str, parser: fn(&str) -> Result<u64>) -> Result<ArrowTiming> {
    let (left, right) = line
        .split_once("-->")
        .ok_or_else(|| anyhow!("invalid subtitle timing line: {line}"))?;
    let start = parser(left.trim())?;
    let right = right.trim();
    let end_token_length = right.find(char::is_whitespace).unwrap_or(right.len());
    let end = parser(&right[..end_token_length])?;
    if end <= start {
        bail!("subtitle cue end must be later than start: {line}");
    }
    Ok(ArrowTiming {
        start,
        end,
        suffix: right[end_token_length..].to_string(),
    })
}

fn clip_interval(
    cue_start: u64,
    cue_end: u64,
    clip_start: u64,
    clip_end: Option<u64>,
) -> Option<(u64, u64)> {
    let clipped_start = cue_start.max(clip_start);
    let clipped_end = clip_end.map_or(cue_end, |end| cue_end.min(end));
    (clipped_end > clipped_start).then_some((clipped_start - clip_start, clipped_end - clip_start))
}

fn parse_srt_timestamp(value: &str) -> Result<u64> {
    parse_clock_timestamp(value, ',', 3, false)
        .with_context(|| format!("invalid SRT timestamp {value:?}"))
}

fn parse_vtt_timestamp(value: &str) -> Result<u64> {
    parse_clock_timestamp(value, '.', 3, true)
        .with_context(|| format!("invalid VTT timestamp {value:?}"))
}

fn parse_ass_timestamp(value: &str) -> Result<u64> {
    parse_clock_timestamp(value.trim(), '.', 2, false)
        .with_context(|| format!("invalid ASS/SSA timestamp {value:?}"))
}

fn parse_clock_timestamp(
    value: &str,
    fraction_separator: char,
    fraction_digits: usize,
    allow_missing_hours: bool,
) -> Result<u64> {
    let (clock, fraction) = value
        .rsplit_once(fraction_separator)
        .ok_or_else(|| anyhow!("missing fractional separator"))?;
    if fraction.len() != fraction_digits || !fraction.chars().all(|ch| ch.is_ascii_digit()) {
        bail!("invalid fractional part");
    }
    let parts: Vec<_> = clock.split(':').collect();
    let (hours, minutes, seconds) = match parts.as_slice() {
        [hours, minutes, seconds] => (*hours, *minutes, *seconds),
        [minutes, seconds] if allow_missing_hours => ("0", *minutes, *seconds),
        _ => bail!("invalid clock part"),
    };
    if ![hours, minutes, seconds]
        .iter()
        .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()))
    {
        bail!("invalid clock digits");
    }
    let hours: u64 = hours.parse()?;
    let minutes: u64 = minutes.parse()?;
    let seconds: u64 = seconds.parse()?;
    if minutes > 59 || seconds > 59 {
        bail!("minutes and seconds must be 00-59");
    }
    let fraction: u64 = fraction.parse()?;
    let fraction_ms = match fraction_digits {
        3 => fraction,
        2 => fraction * 10,
        _ => unreachable!(),
    };
    Ok((hours * 3600 + minutes * 60 + seconds) * 1000 + fraction_ms)
}

fn format_srt_timestamp(milliseconds: u64) -> String {
    format_timestamp(milliseconds, ',', 3, true)
}

fn format_vtt_timestamp(milliseconds: u64) -> String {
    format_timestamp(milliseconds, '.', 3, true)
}

fn format_ass_timestamp(milliseconds: u64) -> String {
    format_timestamp(milliseconds, '.', 2, false)
}

fn format_timestamp(
    milliseconds: u64,
    fraction_separator: char,
    fraction_digits: usize,
    pad_hours: bool,
) -> String {
    let total_seconds = milliseconds / 1000;
    let hours = total_seconds / 3600;
    let minutes = total_seconds % 3600 / 60;
    let seconds = total_seconds % 60;
    let fraction = match fraction_digits {
        3 => milliseconds % 1000,
        2 => milliseconds % 1000 / 10,
        _ => unreachable!(),
    };
    let hours = if pad_hours {
        format!("{hours:02}")
    } else {
        hours.to_string()
    };
    format!("{hours}:{minutes:02}:{seconds:02}{fraction_separator}{fraction:0fraction_digits$}")
}

fn normalize_newlines(source: &str) -> String {
    source.replace("\r\n", "\n").replace('\r', "\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trims_and_rebases_srt_cues() {
        let source =
            "1\n00:00:01,000 --> 00:00:04,000\nfirst\n\n2\n00:00:05,500 --> 00:00:09,000\nsecond\n";
        let output = trim_subtitle(source, SubtitleFormat::Srt, 3000, Some(7000)).unwrap();
        assert_eq!(
            output,
            "1\n00:00:00,000 --> 00:00:01,000\nfirst\n\n2\n00:00:02,500 --> 00:00:04,000\nsecond\n"
        );
    }

    #[test]
    fn trims_vtt_and_preserves_settings() {
        let source = "WEBVTT\n\ncue-a\n00:00:02.000 --> 00:00:06.000 align:start\nhello\n";
        let output = trim_subtitle(source, SubtitleFormat::Vtt, 4000, Some(5000)).unwrap();
        assert_eq!(
            output,
            "WEBVTT\n\ncue-a\n00:00:00.000 --> 00:00:01.000 align:start\nhello\n"
        );
    }

    #[test]
    fn trims_ass_dialogue() {
        let source = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:02.00,0:00:06.00,Default,,0,0,0,,Hello, world\n";
        let output = trim_subtitle(source, SubtitleFormat::Ass, 4000, Some(5000)).unwrap();
        assert!(output.contains("Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hello, world"));
    }
}
