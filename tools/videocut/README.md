# avcut

`avcut` cuts a video at exact whole-second boundaries and keeps a sidecar
subtitle synchronized with the new timeline. It uses the installed `ffmpeg`
and `ffprobe` commands.

## Install

```bash
make install-local
```

The binary is installed at `~/.local/bin/avcut`.

## Usage

```bash
avcut <video> \
  [-b|--start <hh:mm:ss>] \
  [-e|--end <hh:mm:ss>] \
  [-s|--subtitle <path>] \
  [-o|--out <video-path>] \
  [--subtitle-out <path>] \
  [--overwrite] \
  [--dry-run] \
  [--json]
```

`--start` defaults to `00:00:00`. When `--end` is omitted, the clip continues
to the end of the video. Times must use `hh:mm:ss`; minutes and seconds must be
between `00` and `59`.

When `--subtitle` is omitted, `avcut` searches beside the video for an exact
same-stem subtitle in this order: `.srt`, `.vtt`, `.ass`, `.ssa`. If no match is
found, it cuts only the video. Subtitle cues that overlap the selected interval
are clipped to the interval and shifted so the new video begins at `00:00:00`.

```bash
avcut ./movie.mp4 -b 00:01:30 -e 00:03:00 -o ./clip.mp4
avcut ./movie.mp4 -b 00:01:30 -s ./captions.srt --dry-run
```

By default, output files are written beside the input using a name such as:

```text
movie.cut-00-01-30-00-03-00.mp4
movie.cut-00-01-30-00-03-00.srt
```

Use `--out` and `--subtitle-out` for explicit paths, `--overwrite` to replace
existing outputs, and `--dry-run` to inspect the complete plan without writing.

## JSON policy

With `--json`, stdout contains JSON only. Successful runs return an object
beginning with `{"ok":true}`. Failures return a nonzero exit code and:

```json
{"ok":false,"error":{"kind":"runtime","message":"..."}}
```
