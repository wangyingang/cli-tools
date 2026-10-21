# sbvm

Display label: `sing-box version manager`

`sbvm` is a small local version manager for `SagerNet/sing-box`.

It can:

- list remote releases from GitHub
- download a precompiled release asset into `~/.sbvm`
- list installed versions
- activate an installed version by copying or linking `sing-box` into `~/.local/bin`
- uninstall installed versions

## Commands

```bash
sbvm --help
sbvm doctor
sbvm ls-remote
sbvm ls-remote --limit 10
sbvm ls-remote --limit 20 --release
sbvm install v1.13.9
sbvm install latest
sbvm ls
sbvm use v1.13.9
sbvm use v1.13.9 --link
sbvm uninstall v1.13.9
sbvm current
sbvm request /repos/SagerNet/sing-box/releases/latest
```

## Install

```bash
cd ~/Development/Working/clis/sbvm
make install-local
```

## Auth

Public release reads work without auth.

If you want a higher GitHub API rate limit, set:

```bash
export GITHUB_TOKEN=ghp_xxx
```

## Local layout

```text
~/.sbvm/
  downloads/
  versions/<tag>/
  state.json
```

## JSON policy

All commands support a global `--json` flag.

- Success responses are printed as JSON to stdout.
- Human-oriented progress and diagnostics go to stderr.
- Failures return a non-zero exit code.
- Under `--json`, failures use this shape:

```json
{
  "error": {
    "message": "human readable error"
  }
}
```

Examples:

```bash
sbvm --json doctor
sbvm --json ls-remote
sbvm --json ls-remote --limit 10
sbvm --json ls-remote --limit 20 --release
sbvm --json install v1.13.9
sbvm --json request /repos/SagerNet/sing-box/releases/latest
```

## ls-remote filtering

`sbvm ls-remote` limits output size to keep response time lower for repositories with many releases.

- Default limit is `20`
- Use `--limit <N>` to change how many versions are shown
- Use `--release` to exclude all prereleases
- A leading `*` means the version is already installed locally
