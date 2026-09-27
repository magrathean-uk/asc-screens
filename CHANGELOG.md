# Releases

The package metadata currently declares version `2.1.1`. The unreleased section
records behavior present in the checkout; it does not identify a published release.

## Unreleased

- iPhone export uses the largest portrait size in the local target table,
  `1320x2868`.
- Built-in checks cover image format, configured dimensions and PNG transparency.
- `--check` validates existing images without framing, subject to the input
  discovery limitations described in the [README](README.md).
- Device aliases include `iphone-latest`, `ipad-latest`, `mac-latest` and
  `all-latest`. They select sizes from the local target table.
- JSON configuration supports repeatable builds.
- Successful screenshot output produces review JSON, an HTML contact sheet and
  an upload manifest.
- Locale copy files group screenshots for upload; iPhone and iPad caption templates
  place text above or below the frame.
- Mac exports resize screenshots to the configured Mac target without a frame.
- Preview-video export uses FFmpeg to produce H.264 video with silent AAC audio.
- `asc-screens-ci` fingerprints configured inputs and uses completion markers to
  gate replacement uploads through an external `asc` executable.

## v2.1.1

- Added agent workflow notes.
- Kept local screenshot input folders out of git.

## v2.1.0

- Added guided `asc-gen` CLI.
- Recursive screenshot discovery now handles nested folders.
- Screenshot input supports PNG, JPG, JPEG, HEIC, HEIF, TIF, and TIFF.
- Failed screenshots are skipped with a clear message so the rest still render.
- iPhone output uses the largest accepted App Store portrait size.

## v2.0.0

- Background prompt now takes 1 to 3 colors.
- Single color still expands into a 3-stop hue palette.
- Two colors now fill the middle stop automatically.

## v1.0.0

- First public CLI for ASC screenshots.
- Auto-detects iPhone and iPad by image size.
- Frames screenshots and writes ASC-sized PNGs.
