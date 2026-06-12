mod media;
mod subtitle;
mod timecode;

use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use anyhow::{Context, Result, anyhow, bail};
use clap::Parser;
use serde_json::{Value, json};

use crate::media::{command_path, keyframes_around, probe_duration};
use crate::subtitle::{SubtitleFormat, trim_subtitle};
use crate::timecode::{format_hhmmss, parse_hhmmss};

#[derive(Parser)]
#[command(
    name = "avcut",
    version,
    about = "Cut video at outward-aligned keyframes and keep sidecar subtitles synchronized"
)]
struct Cli {
    /// Input video path
    video: PathBuf,

    /// Inclusive start time in hh:mm:ss (default: 00:00:00)
    #[arg(short = 'b', long, value_name = "hh:mm:ss")]
    start: Option<String>,

    /// End time in hh:mm:ss (default: end of video)
    #[arg(short = 'e', long, value_name = "hh:mm:ss")]
    end: Option<String>,

    /// Explicit sidecar subtitle (.srt, .vtt, .ass, or .ssa)
    #[arg(short = 's', long, value_name = "PATH")]
    subtitle: Option<PathBuf>,

    /// Output video path
    #[arg(short = 'o', long, value_name = "PATH")]
    out: Option<PathBuf>,

    /// Re-encode at the requested boundaries instead of copying at nearby keyframes
    #[arg(long)]
    encode: bool,

    /// Replace existing output files
    #[arg(long)]
    overwrite: bool,

    /// Show the resolved plan without writing files
    #[arg(long)]
    dry_run: bool,

    /// Emit stable machine-readable JSON to stdout
    #[arg(long)]
    json: bool,
}

struct CommandOutput {
    human: String,
    json: Value,
}

fn main() -> ExitCode {
    let json_requested = env::args_os().any(|arg| arg == "--json");
    let cli = match Cli::try_parse() {
        Ok(cli) => cli,
        Err(error) => {
            if json_requested {
                println!(
                    "{}",
                    json!({
                        "ok": false,
                        "error": {
                            "kind": "arguments",
                            "message": error.to_string()
                        }
                    })
                );
            } else {
                let _ = error.print();
            }
            return ExitCode::from(2);
        }
    };

    match cut(&cli) {
        Ok(output) => {
            if cli.json {
                println!("{}", output.json);
            } else if !output.human.is_empty() {
                println!("{}", output.human);
            }
            ExitCode::SUCCESS
        }
        Err(error) => {
            if cli.json {
                println!(
                    "{}",
                    json!({
                        "ok": false,
                        "error": {
                            "kind": "runtime",
                            "message": format!("{error:#}")
                        }
                    })
                );
            } else {
                eprintln!("error: {error:#}");
            }
            ExitCode::FAILURE
        }
    }
}

fn cut(args: &Cli) -> Result<CommandOutput> {
    validate_input_file(&args.video, "video")?;
    command_path("ffmpeg").ok_or_else(|| anyhow!("ffmpeg was not found on PATH"))?;
    command_path("ffprobe").ok_or_else(|| anyhow!("ffprobe was not found on PATH"))?;

    let start = parse_hhmmss(args.start.as_deref().unwrap_or("00:00:00"))?;
    let end = args.end.as_deref().map(parse_hhmmss).transpose()?;
    if let Some(end) = end
        && end <= start
    {
        bail!("end time must be later than start time");
    }

    let duration = probe_duration(&args.video)?;
    if start as f64 >= duration {
        bail!("start time is outside the video duration ({duration:.3} seconds)");
    }
    if let Some(end) = end
        && end as f64 > duration + 0.01
    {
        bail!("end time is outside the video duration ({duration:.3} seconds)");
    }

    let requested_start = start as f64;
    let actual_start = if args.encode {
        requested_start
    } else if start == 0 {
        0.0
    } else {
        let keyframe = keyframes_around(&args.video, requested_start)?
            .previous
            .ok_or_else(|| {
                anyhow!("no keyframe found before requested start {requested_start:.3}s")
            })?;
        let error = requested_start - keyframe;
        if error > 1.0 + f64::EPSILON {
            bail!(
                "previous keyframe is {error:.3} seconds before requested start (requested {:.3}s, keyframe {:.3}s); rerun with --encode for exact cutting",
                requested_start,
                keyframe
            );
        }
        keyframe
    };

    let requested_end = end.map(|value| value as f64);
    let actual_end = if args.encode {
        requested_end
    } else if let Some(requested_end) = requested_end {
        let next = keyframes_around(&args.video, requested_end)?.next;
        let boundary = next.unwrap_or(duration);
        let error = boundary - requested_end;
        if error < -0.001 {
            bail!("no keyframe or EOF found after requested end {requested_end:.3}s");
        }
        if error > 1.0 + f64::EPSILON {
            bail!(
                "next keyframe is {error:.3} seconds after requested end (requested {:.3}s, keyframe {:.3}s); rerun with --encode for exact cutting",
                requested_end,
                boundary
            );
        }
        Some(boundary)
    } else {
        None
    };
    let start_error = round_seconds(requested_start - actual_start);
    let end_error = actual_end
        .zip(requested_end)
        .map(|(actual, requested)| round_seconds(actual - requested));

    if let Some(actual_end) = actual_end
        && actual_start >= actual_end
    {
        bail!(
            "aligned start {actual_start:.3}s is not before aligned end {actual_end:.3}s; rerun with --encode"
        );
    }

    let video_out = args
        .out
        .clone()
        .unwrap_or_else(|| default_video_output(&args.video, start, end));
    ensure_distinct_paths(&args.video, &video_out)?;
    ensure_output_available(&video_out, args.overwrite)?;

    let subtitle_in = if let Some(path) = &args.subtitle {
        validate_input_file(path, "subtitle")?;
        Some(path.clone())
    } else {
        discover_subtitle(&args.video)?
    };

    let subtitle_plan = if let Some(input) = subtitle_in {
        let format = SubtitleFormat::from_path(&input)?;
        let output = default_subtitle_output(&video_out, &input);
        ensure_distinct_paths(&input, &output)?;
        ensure_output_available(&output, args.overwrite)?;
        let source = fs::read_to_string(&input)
            .with_context(|| format!("failed to read subtitle {}", input.display()))?;
        Some((input, output, source, format))
    } else {
        None
    };

    let ffmpeg_args = build_ffmpeg_args(
        &args.video,
        &video_out,
        actual_start,
        actual_end,
        args.overwrite,
        args.encode,
    );
    let command_display = shell_command_display("ffmpeg", &ffmpeg_args);
    let subtitle_json = subtitle_plan
        .as_ref()
        .map(|(input, output, _, format)| {
            Ok::<_, anyhow::Error>(json!({
                "input": absolute_path(input)?,
                "output": absolute_path(output)?,
                "format": format.as_str()
            }))
        })
        .transpose()?;

    let plan_json = json!({
        "ok": true,
        "dry_run": args.dry_run,
        "video": {
            "input": absolute_path(&args.video)?,
            "output": absolute_path(&video_out)?,
            "mode": if args.encode { "encode" } else { "copy" },
            "requested_start": format_hhmmss(start),
            "actual_start_seconds": actual_start,
            "start_error_seconds": start_error,
            "requested_end": end.map(format_hhmmss),
            "actual_end_seconds": actual_end,
            "end_error_seconds": end_error,
            "ffmpeg_argv": ffmpeg_args.iter().map(|arg| arg.to_string_lossy()).collect::<Vec<_>>()
        },
        "subtitle": subtitle_json,
    });

    if args.dry_run {
        let subtitle_line = subtitle_plan.as_ref().map_or_else(
            || "subtitle: none".to_string(),
            |(input, output, _, format)| {
                format!(
                    "subtitle: {} -> {} ({})",
                    input.display(),
                    output.display(),
                    format.as_str()
                )
            },
        );
        return Ok(CommandOutput {
            human: format!(
                "dry run\nmode: {}\nrequested start: {}\nactual start: {:.3}s\nactual end: {}\nvideo: {} -> {}\n{}\ncommand: {}",
                if args.encode { "encode" } else { "copy" },
                format_hhmmss(start),
                actual_start,
                actual_end.map_or_else(|| "EOF".to_string(), |value| format!("{value:.3}s")),
                args.video.display(),
                video_out.display(),
                subtitle_line,
                command_display
            ),
            json: plan_json,
        });
    }

    if let Some(parent) = video_out.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create output directory {}", parent.display()))?;
    }
    let output = Command::new("ffmpeg")
        .args(&ffmpeg_args)
        .output()
        .context("failed to start ffmpeg")?;
    if !output.status.success() {
        bail!(
            "ffmpeg failed with status {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    let output_duration = probe_duration(&video_out)?;
    let measured_end = actual_start + output_duration;
    let subtitle_end = actual_end.map_or(measured_end, |aligned_end| aligned_end.min(measured_end));

    if let Some((_, output, source, format)) = &subtitle_plan {
        let clip_start_ms = seconds_to_milliseconds(actual_start);
        let clip_end_ms = seconds_to_milliseconds(subtitle_end);
        let trimmed = trim_subtitle(source, *format, clip_start_ms, Some(clip_end_ms))?;
        if let Some(parent) = output.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create subtitle output directory {}",
                    parent.display()
                )
            })?;
        }
        fs::write(output, trimmed)
            .with_context(|| format!("failed to write subtitle {}", output.display()))?;
    }

    let subtitle_human = subtitle_plan
        .as_ref()
        .map(|(_, output, _, _)| format!("\nsubtitle: {}", output.display()))
        .unwrap_or_default();
    Ok(CommandOutput {
        human: format!("video: {}{}", video_out.display(), subtitle_human),
        json: json!({
            "ok": true,
            "dry_run": false,
            "video": {
                "input": absolute_path(&args.video)?,
                "output": absolute_path(&video_out)?,
                "mode": if args.encode { "encode" } else { "copy" },
                "requested_start": format_hhmmss(start),
                "actual_start_seconds": actual_start,
                "start_error_seconds": start_error,
                "requested_end": end.map(format_hhmmss),
                "aligned_end_seconds": actual_end,
                "end_error_seconds": end_error,
                "output_duration_seconds": output_duration,
                "subtitle_end_seconds": subtitle_end
            },
            "subtitle": subtitle_json
        }),
    })
}

fn build_ffmpeg_args(
    input: &Path,
    output: &Path,
    start: f64,
    end: Option<f64>,
    overwrite: bool,
    encode: bool,
) -> Vec<OsString> {
    let mut args = vec![
        OsString::from(if overwrite { "-y" } else { "-n" }),
        OsString::from("-hide_banner"),
        OsString::from("-ss"),
        OsString::from(format_seconds(start)),
        OsString::from("-i"),
        input.as_os_str().to_os_string(),
    ];
    if let Some(end) = end {
        args.extend([
            OsString::from("-t"),
            OsString::from(format_seconds(end - start)),
        ]);
    }
    args.extend([
        OsString::from("-map"),
        OsString::from("0:v:0?"),
        OsString::from("-map"),
        OsString::from("0:a?"),
    ]);
    if encode {
        args.extend([
            OsString::from("-c:v"),
            OsString::from("libx264"),
            OsString::from("-preset"),
            OsString::from("medium"),
            OsString::from("-crf"),
            OsString::from("18"),
            OsString::from("-c:a"),
            OsString::from("aac"),
        ]);
    } else {
        args.extend([OsString::from("-c"), OsString::from("copy")]);
    }
    args.extend([
        OsString::from("-avoid_negative_ts"),
        OsString::from("make_zero"),
    ]);
    if matches!(
        output
            .extension()
            .and_then(OsStr::to_str)
            .map(|ext| ext.to_ascii_lowercase())
            .as_deref(),
        Some("mp4" | "mov" | "m4v")
    ) {
        args.extend([OsString::from("-movflags"), OsString::from("+faststart")]);
    }
    args.push(output.as_os_str().to_os_string());
    args
}

fn format_seconds(seconds: f64) -> String {
    format!("{seconds:.3}")
}

fn round_seconds(seconds: f64) -> f64 {
    (seconds * 1000.0).round() / 1000.0
}

fn seconds_to_milliseconds(seconds: f64) -> u64 {
    (seconds * 1000.0).round().max(0.0) as u64
}

fn discover_subtitle(video: &Path) -> Result<Option<PathBuf>> {
    let parent = video.parent().unwrap_or_else(|| Path::new("."));
    let stem = video
        .file_stem()
        .ok_or_else(|| anyhow!("video path has no file stem: {}", video.display()))?;
    for extension in ["srt", "vtt", "ass", "ssa"] {
        let candidate = parent.join(stem).with_extension(extension);
        if candidate.is_file() {
            return Ok(Some(candidate));
        }
        let uppercase = parent
            .join(stem)
            .with_extension(extension.to_ascii_uppercase());
        if uppercase.is_file() {
            return Ok(Some(uppercase));
        }
    }
    Ok(None)
}

fn default_video_output(video: &Path, start: u64, end: Option<u64>) -> PathBuf {
    let parent = video.parent().unwrap_or_else(|| Path::new("."));
    let stem = video
        .file_stem()
        .unwrap_or_else(|| OsStr::new("video"))
        .to_string_lossy();
    let extension = video.extension().and_then(OsStr::to_str).unwrap_or("mp4");
    let start = format_hhmmss(start).replace(':', "-");
    let end = end
        .map(format_hhmmss)
        .unwrap_or_else(|| "end".to_string())
        .replace(':', "-");
    parent.join(format!("{stem}.cut-{start}-{end}.{extension}"))
}

fn default_subtitle_output(video_out: &Path, subtitle_in: &Path) -> PathBuf {
    let extension = subtitle_in
        .extension()
        .and_then(OsStr::to_str)
        .unwrap_or("srt");
    video_out.with_extension(extension)
}

fn validate_input_file(path: &Path, label: &str) -> Result<()> {
    if !path.is_file() {
        bail!("{label} file does not exist: {}", path.display());
    }
    Ok(())
}

fn ensure_output_available(path: &Path, overwrite: bool) -> Result<()> {
    if path.exists() && !overwrite {
        bail!(
            "output already exists: {} (use --overwrite to replace it)",
            path.display()
        );
    }
    Ok(())
}

fn ensure_distinct_paths(input: &Path, output: &Path) -> Result<()> {
    if absolute_path(input)? == absolute_path(output)? {
        bail!(
            "input and output paths must be different: {}",
            input.display()
        );
    }
    Ok(())
}

fn absolute_path(path: &Path) -> Result<PathBuf> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(env::current_dir()?.join(path))
    }
}

fn shell_command_display(command: &str, args: &[OsString]) -> String {
    std::iter::once(OsStr::new(command))
        .chain(args.iter().map(OsString::as_os_str))
        .map(shell_quote)
        .collect::<Vec<_>>()
        .join(" ")
}

fn shell_quote(value: &OsStr) -> String {
    let value = value.to_string_lossy();
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "_./:@%+=,-".contains(ch))
    {
        value.into_owned()
    } else {
        format!("'{}'", value.replace('\'', "'\\''"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_short_options() {
        let cli = Cli::try_parse_from([
            "avcut",
            "input.mp4",
            "-b",
            "00:00:05",
            "-e",
            "00:01:00",
            "-s",
            "captions.srt",
            "-o",
            "clip.mp4",
        ])
        .unwrap();

        assert_eq!(cli.video, PathBuf::from("input.mp4"));
        assert_eq!(cli.start.as_deref(), Some("00:00:05"));
        assert_eq!(cli.end.as_deref(), Some("00:01:00"));
        assert_eq!(cli.subtitle, Some(PathBuf::from("captions.srt")));
        assert_eq!(cli.out, Some(PathBuf::from("clip.mp4")));
        assert!(!cli.encode);
    }

    #[test]
    fn derives_subtitle_output_from_video_output() {
        let output = default_subtitle_output(
            Path::new("/tmp/scenes/clip.mp4"),
            Path::new("/videos/source.ass"),
        );
        assert_eq!(output, PathBuf::from("/tmp/scenes/clip.ass"));
    }

    #[test]
    fn builds_exact_duration_ffmpeg_args() {
        let args = build_ffmpeg_args(
            Path::new("input.mp4"),
            Path::new("output.mp4"),
            65.25,
            Some(125.0),
            false,
            false,
        );
        let args: Vec<_> = args.iter().map(|arg| arg.to_string_lossy()).collect();
        assert!(args.windows(2).any(|pair| pair == ["-ss", "65.250"]));
        assert!(args.windows(2).any(|pair| pair == ["-t", "59.750"]));
        assert!(args.windows(2).any(|pair| pair == ["-c", "copy"]));
    }

    #[test]
    fn builds_encode_args() {
        let args = build_ffmpeg_args(
            Path::new("input.mp4"),
            Path::new("output.mp4"),
            65.0,
            Some(125.0),
            false,
            true,
        );
        let args: Vec<_> = args.iter().map(|arg| arg.to_string_lossy()).collect();
        assert!(args.windows(2).any(|pair| pair == ["-c:v", "libx264"]));
        assert!(!args.windows(2).any(|pair| pair == ["-c", "copy"]));
    }

    #[test]
    fn names_default_output_from_time_range() {
        let output = default_video_output(Path::new("/tmp/movie.mp4"), 5, Some(65));
        assert_eq!(
            output,
            PathBuf::from("/tmp/movie.cut-00-00-05-00-01-05.mp4")
        );
    }
}
