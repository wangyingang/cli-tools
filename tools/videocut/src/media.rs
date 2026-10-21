use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};
use serde::Deserialize;

#[derive(Deserialize)]
struct ProbeResponse {
    format: ProbeFormat,
}

#[derive(Deserialize)]
struct ProbeFormat {
    duration: String,
}

#[derive(Deserialize)]
struct PacketResponse {
    #[serde(default)]
    packets: Vec<ProbePacket>,
}

#[derive(Deserialize)]
struct ProbePacket {
    pts_time: Option<String>,
    flags: Option<String>,
}

#[derive(Debug, PartialEq)]
pub struct KeyframeBounds {
    pub previous: Option<f64>,
    pub next: Option<f64>,
}

pub fn command_path(name: &str) -> Option<PathBuf> {
    let path = env::var_os("PATH")?;
    env::split_paths(&path)
        .map(|directory| directory.join(name))
        .find(|candidate| candidate.is_file())
}

pub fn probe_duration(video: &Path) -> Result<f64> {
    let output = Command::new("ffprobe")
        .args([
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
        ])
        .arg(video)
        .output()
        .context("failed to start ffprobe")?;
    if !output.status.success() {
        bail!(
            "ffprobe failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let response: ProbeResponse = serde_json::from_slice(&output.stdout)
        .context("failed to parse ffprobe duration response")?;
    let duration = response
        .format
        .duration
        .parse::<f64>()
        .context("ffprobe returned an invalid duration")?;
    if !duration.is_finite() || duration <= 0.0 {
        bail!("ffprobe returned a non-positive duration");
    }
    Ok(duration)
}

pub fn keyframes_around(video: &Path, target_seconds: f64) -> Result<KeyframeBounds> {
    let window_start = (target_seconds - 5.0).max(0.0);
    let window_end = target_seconds + 5.0;
    let interval = format!("{window_start:.6}%{window_end:.6}");
    let output = Command::new("ffprobe")
        .args([
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-read_intervals",
            &interval,
            "-show_packets",
            "-show_entries",
            "packet=pts_time,flags",
            "-of",
            "json",
        ])
        .arg(video)
        .output()
        .context("failed to start ffprobe while locating keyframes")?;
    if !output.status.success() {
        bail!(
            "ffprobe keyframe lookup failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    let response: PacketResponse = serde_json::from_slice(&output.stdout)
        .context("failed to parse ffprobe keyframe response")?;
    let timestamps: Vec<f64> = response
        .packets
        .into_iter()
        .filter(|packet| {
            packet
                .flags
                .as_deref()
                .is_some_and(|flags| flags.contains('K'))
        })
        .filter_map(|packet| packet.pts_time?.parse::<f64>().ok())
        .filter(|timestamp| timestamp.is_finite() && *timestamp >= 0.0)
        .collect();

    let previous = timestamps
        .iter()
        .copied()
        .filter(|timestamp| *timestamp <= target_seconds)
        .max_by(f64::total_cmp);
    let next = timestamps
        .iter()
        .copied()
        .filter(|timestamp| *timestamp >= target_seconds)
        .min_by(f64::total_cmp);

    Ok(KeyframeBounds { previous, next })
}
