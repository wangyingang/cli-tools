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
