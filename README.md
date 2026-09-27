<p align="center">
  <img src="https://raw.githubusercontent.com/magrathean-uk/magrathean-uk/main/assets/icons/asc-screens.png" width="96" height="96" alt="">
</p>

<h1 align="center">asc-screens</h1>

<p align="center">A local CLI that turns iPhone, iPad and Mac captures into App Store Connect screenshot sets.</p>

<p align="center">
  <a href="docs/index.md">Documentation</a>
</p>

## Overview

asc-screens frames phone and tablet captures, scales Mac captures, adds optional captions, validates image dimensions and transparency, and writes review and upload manifests. It installs from a source checkout and runs locally or in CI; there is no published package.

## Features

- Frames iPhone and iPad captures with Apple Frames onto a generated background
- Scales Mac captures directly to the target dimensions, without a frame
- Optional caption templates driven by a locale-keyed copy file
- Validates image format, configured dimensions and PNG transparency
- Writes an HTML contact sheet plus JSON review and upload manifests
- Converts an MP4 to a silent, App Store-oriented preview video
- Fingerprints design inputs and delegates upload to the external `asc` CLI

## Getting started

Requirements:

- Python 3.10 or later
- ImageMagick, with `magick` on `PATH`
- Apple Frames CLI, with `frames` on `PATH` or supplied with `--frames-bin`
- `ffmpeg` on `PATH`, for App-preview video generation only

Clone or otherwise obtain a checkout, then run from that checkout:

```bash
python3 -m pip install -e .
```

The editable install registers three commands: `asc-screens`, `asc-gen`, and `asc-screens-ci`. ImageMagick, Apple Frames and FFmpeg are external tools and must be installed separately.

### Build screenshots

The direct command accepts a directory containing nested `iphone/`, `ipad/`, or `mac/` folders, or a mixed directory. If named device subdirectories exist, discovery uses them and ignores loose mixed inputs. Otherwise, it classifies files by aspect ratio; this is a heuristic, so inspect the selected family. It reads PNG, JPG, JPEG, HEIC, HEIF, TIF, and TIFF source files.

```bash
asc-screens ./source
```

The default output is `asc_out/`. Phone and tablet inputs are framed with Apple Frames and composited onto a generated background. Mac inputs are resized directly to the selected dimensions, which can change their aspect ratio; they do not receive frames, backgrounds or captions. The CLI still checks for Apple Frames before any screenshot build, including Mac-only builds. Existing generated folders named `asc_out` and `_framed` are excluded from source discovery.

Choose a device lane and output options explicitly:

```bash
asc-screens ./source --kind iphone-latest
asc-screens ./source --kind ipad-latest --template title-bottom
asc-screens ./source --kind mac
asc-screens ./source --background '#060914,#1A26FF,#20D7E8'
```

Available `--kind` values are `iphone`, `ipad`, `mac`, `all`, `iphone-latest`, `ipad-latest`, `mac-latest`, and `all-latest`. The default targets in this checkout are `1320x2868` for iPhone, `2064x2752` for iPad, and `2880x1800` for Mac.

Without a configuration file, the direct CLI prompts for a background even when `--background` is supplied. Configuration mode skips this prompt. Backgrounds accept one to three hex colours. One colour expands to a three-stop palette; two colours receive an interpolated middle stop. The built-in themes are `teslatlas` and `purple`.

The caption templates are `plain`, `title-top`, and `title-bottom`. A JSON copy file maps locales to `title` and `subtitle` values:

```json
{
  "en-GB": {
    "title": "Fast EV planning",
    "subtitle": "Route, charge, arrive"
  },
  "de-DE": {
    "title": "Schnelle EV Planung",
    "subtitle": "Route, laden, ankommen"
  }
}
```

Build every locale or select one locale:

```bash
asc-screens ./source --copy-file copy.json --template title-bottom
asc-screens ./source --copy-file copy.json --locale en-GB --template title-top
```

Without a copy file, caption templates use the source filename as the title and remove a trailing `-ipad` or `-iphone` suffix. `plain` does not render copy text.

### Repeatable configuration

Use JSON when paths and options should be recorded in a project file:

```json
{
  "source": "./source",
  "output_root": "asc_out",
  "kind": "all-latest",
  "template": "title-bottom",
  "copy_file": "copy.json",
  "validate": true
}
```

Run it with:

```bash
asc-screens --config asc-screens.json
```

Relative `source`, `output_root`, and `copy_file` paths are resolved relative to the configuration file.

### Guided mode

Guided mode is available from a checkout with:

```bash
./asc-gen.py
```

It prompts for the source directory, build or check mode, device lane, background, copy file, template, locale, and output directory. The installed `asc-gen` command invokes the same guided wrapper. It is interactive and does not provide a separate noninteractive help flow.

### Output and validation

Images go under `asc_out/<family>/`, or `asc_out/<locale>/<family>/` with locale copy. Framing intermediates go under `_framed` within the build root. Builds that produce images also write:

- `asc_review.html`, a visual contact sheet;
- `asc_review.json`, an ordered review manifest;
- `asc_upload.json`, grouped by locale and device family for an upload tool.

Use `--check` to validate an existing directory of screenshot files without framing:

```bash
asc-screens --check ./existing-screenshots
```

Discovery skips paths containing `asc_out` or `_framed`, including in check mode. To check exported images separately, copy them into a directory without those names. Check mode classifies by dimensions even when named device folders were used for rendering.

Validation accepts PNG, JPG, and JPEG files only. It checks the local target table and rejects PNG transparency. The table contains these portrait iPhone/iPad dimensions and their landscape reversals, plus the listed Mac sizes:

- iPhone: `1242x2688`, `1284x2778`, `1290x2796`, `1320x2868`;
- iPad: `1488x2266`, `1668x2420`, `2048x2732`, `2064x2752`;
- Mac: `1280x800`, `1440x900`, `2560x1600`, `2880x1800`.

Inspect the output count and contact sheet after a run. Some frame or composite failures are skipped; inputs with the same filename stem can overwrite each other. The renderer does not clear old output files. Local checks do not establish current App Store submission acceptance.

### App-preview video

Convert an MP4 to a silent, App Store-oriented preview video with `ffmpeg`:

```bash
asc-screens --preview input.mp4 --output-root asc_out
```

The defaults are `886x1920`, 30 fps, and a maximum duration of 30 seconds. The encoder replaces source audio with silent AAC and resizes the video to the requested dimensions. Use `--preview-size WIDTHxHEIGHT`, `--preview-fps`, and `--preview-max-duration` to change them. The output is written under `asc_out/video/` with a filename that records the selected constraints.

### CI upload handoff

`asc-screens-ci` fingerprints configured design inputs and skips work when a matching local cache marker exists. On a cache miss it runs `asc-screens --config ...`, reads `asc_upload.json`, validates `asc` authentication, finds the configured App Store version and locale, then delegates screenshot upload to the external `asc` CLI with `--replace`.

Minimal `.asc-screens-ci.json`:

```json
{
  "app_id": "123456789",
  "version": "1.2.3",
  "asc_screens_config": "asc-screens.json",
  "output_root": "asc_out"
}
```

By default the fingerprint includes the `asc-screens` config, its `source`, and its `copy_file` when present. It does not include the CI config automatically. Set `design_inputs` to control the paths or glob patterns. The default upload mapping is `iphone` to `IPHONE_69` and `ipad` to `IPAD_PRO_3GEN_129`; Mac is generated locally but has no default CI device mapping. Use the `device_type_map` field for any upload mapping required by the external CLI.

Print the cache key without building or uploading:

```bash
asc-screens-ci --config .asc-screens-ci.json --fingerprint-only
```

Normal runs require an already authenticated `asc` installation and replace remote screenshot sets on a cache miss. Read the configuration, cache and CI integration details in [`docs/asc-upload-ci.md`](docs/asc-upload-ci.md).

### Development

Run the test suite from the checkout:

```bash
python3 -m unittest discover -v
```

Check parser help without rendering:

```bash
python3 asc_screens.py --help
python3 asc_screens_ci.py --help
```

Tests cover Python behavior and mocked external commands. Rendering changes also need a local run and visual review; upload compatibility needs separate verification with the intended external CLI.

## Documentation

- [docs/index.md](docs/index.md) — documentation index
- [docs/asc-upload-ci.md](docs/asc-upload-ci.md) — CI workflow and external upload commands
- [CHANGELOG.md](CHANGELOG.md) — release notes and the unreleased change set
- [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) — contribution guidance
- [.github/SUPPORT.md](.github/SUPPORT.md) — support guidance
- [.github/SECURITY.md](.github/SECURITY.md) — security policy
- [docs/legal/trademarks.md](docs/legal/trademarks.md) — trademark notices
- [docs/legal/third-party-notices.md](docs/legal/third-party-notices.md) — licensing and third-party tool summary

## Licence

asc-screens is open source under the MIT licence. See [LICENSE](LICENSE).

asc-screens is independent. It is not affiliated with, endorsed by or supported by Apple Inc., Apple Frames, ImageMagick Studio LLC or `appshots`.

<sub>© 2026 MAGRATHEAN UK LTD · [Legal](https://github.com/magrathean-uk/.github/blob/main/LEGAL.md)</sub>
