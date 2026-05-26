# Releases

## Unreleased

- Updated iPhone export to the latest accepted App Store lane.
- Added built-in validation for format, size, and PNG transparency.
- Added `--check` mode for validating existing screenshots without framing.
- Added latest-lane aliases to guided and direct CLI flows.
- Added JSON config mode for repeatable runs.
- Added review and upload manifest outputs.
- Added locale copy-file builds for upload grouping.
- Added safe top and bottom caption templates.
- Added `asc-screens-ci` for design-change-gated screenshot upload through `asc`.

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
