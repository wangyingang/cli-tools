use anyhow::{Result, bail};

pub fn parse_hhmmss(value: &str) -> Result<u64> {
    let parts: Vec<_> = value.split(':').collect();
    if parts.len() != 3
        || parts[0].len() < 2
        || parts[1].len() != 2
        || parts[2].len() != 2
        || !parts
            .iter()
            .all(|part| part.chars().all(|ch| ch.is_ascii_digit()))
    {
        bail!("invalid time {value:?}; expected hh:mm:ss");
    }
    let hours: u64 = parts[0].parse()?;
    let minutes: u64 = parts[1].parse()?;
    let seconds: u64 = parts[2].parse()?;
    if minutes > 59 || seconds > 59 {
        bail!("invalid time {value:?}; minutes and seconds must be 00-59");
    }
    Ok(hours * 3600 + minutes * 60 + seconds)
}

pub fn format_hhmmss(total_seconds: u64) -> String {
    let hours = total_seconds / 3600;
    let minutes = total_seconds % 3600 / 60;
    let seconds = total_seconds % 60;
    format!("{hours:02}:{minutes:02}:{seconds:02}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_strict_hhmmss() {
        assert_eq!(parse_hhmmss("00:01:02").unwrap(), 62);
        assert_eq!(parse_hhmmss("100:00:00").unwrap(), 360_000);
        assert!(parse_hhmmss("1:02:03").is_err());
        assert!(parse_hhmmss("00:60:00").is_err());
        assert!(parse_hhmmss("00:00:01.5").is_err());
    }
}
