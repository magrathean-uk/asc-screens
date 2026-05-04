# Releases

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
