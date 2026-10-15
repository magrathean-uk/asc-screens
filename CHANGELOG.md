# Releases

The package metadata currently declares version `2.1.1`. The unreleased section
records behavior present in the checkout; it does not identify a published release.

## Unreleased

- Added a studio finish with smooth full-canvas gradients derived automatically
  from local app icon colours, rounded icons, and device silhouette shadows.
  The background stays quiet beside copy and gains colour behind the product,
  without decorative panels, motifs, outlines, or accent rules. The flat finish
  uses a uniform background; recipes without an icon fall back to their accent.

- Composed iPhone and iPad creatives now use actual Apple Frames device assets,
  including camera cutouts and hardware outlines, with proportional screen
  fitting and device metadata in review manifests.
- Local frame-pack paths expand environment variables and `~`, so recipes can
  use `$BOLYKI_DEV_LIBS/frames-apple401` across machines.

- Added curated per-app campaigns with saved source selections, explicit crops,
  feature copy, local galleries, and source/template fingerprints.
- CI completion markers now change when the shared renderer changes.

- Added composed creative designs with exact app identity, copy fitting, device
  or feature imagery, light/dark palettes, and adaptive wide/portrait layouts.
- Added `--design-file` to direct and guided flows, example Nodex/Termex recipes,
  and CI fingerprinting for recipes and referenced icons.

- Fixed iPhone and iPad caption overlap by reserving measured text space before
  fitting device frames, including top and bottom caption templates.

- Added local image and video exports for product-page headers, search results,
  universal images, and In-App Event cards and details, with dimension and
  media validation, posters, and a creative HTML review.
- Added creative asset profiles to direct JSON configuration and guided mode.
- Added Asset Library upload and explicit existing version, custom-page, and
  optimization-treatment placement targets through `asc-screens-ci`, plus a
  local command-plan dry run.
- Updated the upload handoff for `asc` 5.14.3, including confirmed screenshot
  replacement and fingerprints that include upload targeting configuration.

- The Apple Frames CLI is found through `--frames-bin`, the
  `ASC_SCREENS_FRAMES_BIN` environment variable or `PATH`. The built-in
  `~/.local/bin/frames` default is gone, and `asc-gen` uses the same lookup.
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
