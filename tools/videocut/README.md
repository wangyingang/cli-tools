# avcut

`avcut` cuts a video at exact whole-second boundaries and keeps a sidecar
subtitle synchronized with the new timeline. It uses the installed `ffmpeg`
and `ffprobe` commands.

## Install

```bash
make install-local
avcut --json doctor
```

The binary is installed at `~/.local/bin/avcut`.

## Commands

```bash
avcut --json doctor
avcut --json probe ./movie.mp4
avcut cut ./movie.mp4 --start 00:01:30 --end 00:03:00
avcut cut ./movie.mp4 --start 00:01:30 --subtitle ./captions.srt --dry-run
avcut ffmpeg -- -version
```

`--start` defaults to `00:00:00`. When `--end` is omitted, the clip continues
to the end of the video. Times must use `hh:mm:ss`; minutes and seconds must be
between `00` and `59`.

Unless `--subtitle` or `--no-subtitle` is supplied, `avcut` searches beside the
video for an exact same-stem subtitle in this order: `.srt`, `.vtt`, `.ass`,
`.ssa`. Subtitle cues that overlap the selected interval are clipped to the
interval and shifted so the new video begins at `00:00:00`.

By default, output files are written beside the input using a name such as:

```text
movie.cut-00-01-30-00-03-00.mp4
movie.cut-00-01-30-00-03-00.srt
```

Use `--out` and `--subtitle-out` for explicit paths, `--overwrite` to replace
existing outputs, and `--dry-run` to inspect the complete plan without writing.

## JSON policy

With `--json`, stdout contains JSON only. Diagnostics are included in the
machine-readable error object and credentials are not applicable.

Successful commands return an object beginning with:

```json
{"ok":true}
```

Failures return a nonzero exit code and:

```json
{"ok":false,"error":{"kind":"runtime","message":"..."}}
```

Command families:

```bash
avcut --json doctor
avcut --json probe ./movie.mp4
avcut --json cut ./movie.mp4 --start 00:01:30 --end 00:03:00 --dry-run
avcut --json ffmpeg -- -version
```
