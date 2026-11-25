# Releases

The package metadata currently declares version `2.2.0`. The unreleased section
records behavior present in the checkout; it does not identify a published release.

## Unreleased

## v2.2.0

- Caption wrapping now balances the lines, which reduces one-word last lines where the words fit
  the caption width (two long words can still land on separate lines).
- Added an opt-in golden-image regression check, `ASC_GOLDEN=1 python3 -m unittest test_asc_golden -v`.
  It renders synthetic fixtures (iPhone with a caption, iPad, Mac framed, desktop and fill) through
  ImageMagick, Apple Frames and the Swift/AppKit renderer, and compares them with committed
  references in `tests/golden/`. It is local only and skipped by default.
- Mac screenshots now look like a normal Mac screen on a MacBook Pro: the window
  capture sits in the middle of a desktop with the menu bar (Apple menu, app name,
  menus, status icons, clock) and the Dock (common apps, the app with its running
  dot, Trash), drawn at MacBook Pro M5 16-inch size and framed in Silver with
  Apple Frames on the screenshot background. `--mac-style desktop` gives the
  desktop without the MacBook. System fonts, SF Symbols and real app icons are
  drawn by a Swift/AppKit renderer.
  `--mac-app`, `--mac-app-name`, `--mac-menus`, `--mac-wallpaper`, `--mac-clock`
  and `--mac-dock` configure it; `--mac-style fill` keeps the old full-canvas output.
- Mac-only builds with `--mac-style desktop` or `fill` no longer require Apple Frames.
- An explicit `--background` no longer triggers the background prompt.
- Inputs that would write the same output file stop the run instead of
  silently overwriting each other.
- `asc-screens-ci` maps Mac screenshots to `DESKTOP` by default, refuses to mix
  Mac and iPhone/iPad sets with the wrong platform before uploading, and
  fingerprints the Mac wallpaper, app icon and Dock icons.
- A screenshot build that produces nothing (every input skipped, no input matching `--kind`, or an
  empty source folder) now exits with an error (the guided `asc-gen` too) and leaves the previous
  `asc_upload.json` untouched; a successful build replaces it.
- `asc-screens-ci` gives every build run a unique run id (`ASC_SCREENS_RUN_ID`), which the renderer
  records in `asc_upload.json`. An upload refuses a manifest without its own run id, both before
  planning and again before the first replacement, so output another build wrote into the same
  output folder is never uploaded. An explicit `--dry-run` on an existing manifest (including a
  creative one) does not need a run id.
- `asc-screens-ci` now checks the platform and device type of each screenshot set before running
  any command: iPhone and iPad sets need platform `IOS` (not `TV_OS` or `VISION_OS`), Mac sets need
  `MAC_OS`, and every `device_type_map` value must be a screenshot slot asc supports for its family
  (checked against the `asc screenshots sizes --all` catalogue of asc 5.14.3, so `IPHONE_999`,
  `IPAD_BOGUS` and `IMESSAGE_APP_DESKTOP` are refused). Values are canonicalised as asc does: case
  and surrounding spaces are ignored and `APP_` is optional, so `iphone_67` and `desktop` work.
- Upload manifests are bound to file content: every screenshot and creative asset entry in
  `asc_upload.json` records a `sha256`, and `asc-screens-ci` (normal run, existing-manifest
  `--dry-run`, direct upload) recomputes it before any command is built and again before the first
  replacement. A changed file or an entry without a hash (a manifest from before this change) is
  refused with the file named and a prompt to rebuild, so a rebuild that failed after rendering
  cannot leave a handoff that accepts the changed screenshots.
- `asc_upload.json` and `asc_review.json` are written to a sibling temporary file and atomically
  replaced, so a symlinked manifest is replaced rather than followed and a failed write leaves the
  previous manifest unchanged.
- The golden check validates the full-size output (opaque, App Store size) before comparing, also in
  update mode, bounds its subprocess calls and timeout recovery, kills a run's process group on
  Ctrl-C, and ignores an `ASC_GOLDEN_OUT` inside the checkout (and a system temp directory inside it,
  falling back to `/tmp`).

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
- Mac exports resize screenshots to the configured Mac target; `--mac-style fill` adds no frame
  (the default `framed` style is described under v2.2.0).
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
