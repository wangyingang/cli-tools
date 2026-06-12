# avcut

`avcut` cuts a video and keeps a sidecar subtitle synchronized with the new
timeline. It uses the installed `ffmpeg` and `ffprobe` commands.

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
  [--encode] \
  [--overwrite] \
  [--dry-run] \
  [--json]
```

`--start` defaults to `00:00:00`. When `--end` is omitted, the clip continues
to the end of the video. Times must use `hh:mm:ss`; minutes and seconds must be
between `00` and `59`.

By default, `avcut` copies the original video and audio streams without
re-encoding. It aligns outward so content is not lost: the start moves to the
previous video keyframe and the end moves to the next video keyframe. If either
boundary moves by more than five seconds, the command exits before writing and
asks for `--encode`. Use `--encode` to cut at the requested times by re-encoding
video as H.264 and audio as AAC.

When `--subtitle` is omitted, `avcut` searches beside the video for an exact
same-stem subtitle in this order: `.srt`, `.vtt`, `.ass`, `.ssa`. If no match is
found, it cuts only the video. Subtitle cues are clipped to the actual aligned
video interval and shifted by the actual video start, not the requested start.

```bash
avcut ./movie.mp4 -b 00:01:30 -e 00:03:00 -o ./clip.mp4
avcut ./movie.mp4 -b 00:01:30 -s ./captions.srt --dry-run
avcut ./movie.mp4 -b 00:01:30 -e 00:03:00 --encode
```

By default, output files are written beside the input and named from the actual
aligned begin and end timestamps:

```text
movie.cut-00.59.58.023-01.06.04.mp4
movie.cut-00.59.58.023-01.06.04.srt
```

Each timestamp uses `hh.mm.ss` or `hh.mm.ss.SSS` when milliseconds exist. When
`--end` is omitted, the end component uses the input video EOF timestamp.

When a subtitle is processed, its output is placed beside the output video with
the same stem and the original subtitle extension. Use `-o/--out` to control
both output names, `--overwrite` to replace existing outputs, and `--dry-run`
to inspect the complete plan without writing.

## JSON policy

With `--json`, stdout contains JSON only. Successful runs return an object
beginning with `{"ok":true}`. Failures return a nonzero exit code and:

```json
{"ok":false,"error":{"kind":"runtime","message":"..."}}
```
