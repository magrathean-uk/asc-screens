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
- Exports product-page header, search results, universal, and In-App Event creative images and videos
- Composes branded creative images with fitted copy and adaptive product layouts
- Produces creative video posters and a local HTML review with playback
- Fingerprints design inputs and delegates upload to the external `asc` CLI

## Getting started

Requirements:

- Python 3.11 or later
- ImageMagick, with `magick` on `PATH`
- Apple Frames CLI and its device assets, with `frames` on `PATH`, or supplied with `--frames-bin` or the `ASC_SCREENS_FRAMES_BIN` environment variable. Check assets with `frames doctor`; `FRAMES_ASSETS` can select an existing asset directory.
- `ffmpeg` on `PATH`, for App-preview video generation only

The minimum is Python 3.11 because Python 3.10 reaches its scheduled end of
support in October 2026.

Clone or otherwise obtain a checkout, then run from that checkout. The virtual environment keeps the install inside the checkout instead of a user-level Python location:

```bash
python3 -m venv .venv
. .venv/bin/activate
clean-development run --session session-only -- python3 -m pip install -e .
```

The editable install registers `asc-screens`, `asc-gen`, `asc-screens-ci`, and
`asc-screens-campaign`. ImageMagick, Apple Frames and FFmpeg are external tools
and must be installed separately.

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

Caption templates reserve a separate area for the measured title and subtitle,
then fit the device frame in the remaining space so the frame cannot cover text.

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

### Header, search results, and event creatives

Use a composed design when starting with an app capture. A design recipe adds
app identity, a short headline, supporting copy, and a product image in separate
regions. Wide formats place copy beside the product; portrait formats stack
them. The source image keeps its proportions and complete content.

```bash
asc-screens capture.png --asset creative-all --design-file examples/nodex.design.json
```

The included [Nodex](examples/nodex.design.json) and
[Termex](examples/termex.design.json) recipes demonstrate light and dark designs.
Customize the copy and replace the `icon` path with your app icon. Icon paths
resolve relative to the design JSON. Set `layout` to `hero` or `spotlight`, and
`media_kind` to `iphone`, `ipad`, `image`, `framed`, or `auto`. Phone and tablet
compositions use installed Apple Frames assets, including the actual camera
cutout, screen mask, and physical device outline. The whole framed device is
scaled proportionally into the product region. Scaled native captures are
contained in the matching screen panel before framing, without a cover crop.
Use `image` for a
deliberately selected UI detail, and `framed` for a capture that already includes
its device frame. Explicit line breaks in the headline remain balanced by
reducing type size before adding lines. Long copy fails if it cannot fit legibly.

Device compositions require the local Apple Frames CLI and assets. Configure
Frames normally, set `FRAMES_ASSETS`, or add `frame_assets` to the design JSON.
Paths expand environment variables and `~`; relative paths resolve beside the
recipe. For a local frame pack in the development library, use
`"frame_assets": "$BOLYKI_DEV_LIBS/frames-apple401"` and set `BOLYKI_DEV_LIBS`
to that library's directory. The examples reference an installed local pack;
rendering does not download frame assets. Optional `frame_device` selects a
compatible model variant and `frame_color` selects an available colour. Silver
is preferred when available. `frames_bin` can select a local CLI; direct
`--frames-bin` and `--frame-color` overrides also apply to composed designs.
Missing assets stop the render. Review metadata records the exact device,
colour, screen dimensions and frame dimensions.

Composed designs use the `studio` finish by default: a smooth gradient across
the full canvas, with colours extracted automatically from the local app icon.
The tint stays gentle beside the headline and becomes richer behind the product.
There are no decorative panels, motifs, outlines, or accent rules. Rounded app
icons and shadows from the actual device silhouette give the product depth.
The supplied screenshot remains the product evidence.

Set `"finish": "flat"` for a uniform background. With an icon, its colours drive
the gradient; a recipe's `accent` is used only as a fallback when no icon is
supplied. Legacy `motif` values are accepted but draw nothing. Copy, device
geometry, and screenshot selection are the same under either finish. The icon,
recipe, and shared renderer contribute to campaign and CI fingerprints, so a
colour or template change triggers fresh generation.

Designs support image sources. Existing video conversion remains available in
a separate run without `--design-file`. For universal images, compositions use
a conservative central region to protect copy and product imagery under common
center crops; inspect Apple's placement preview for the final device treatment.

Repeatable renderer configuration accepts `"design_file": "nodex.design.json"`.
Guided mode also accepts a design file. CI fingerprints the recipe and its icon
by default, so copy and identity changes trigger fresh generation and upload.

Apple calls the artwork and videos used in these placements **creative assets**.
A “visual” is simply that image or video. A custom product page is an alternate
page, and product page optimization is a test of alternatives; both can reuse
creative assets rather than requiring another image format. These creative
placements are available on iOS 27 and iPadOS 27 and later.
See [Apple's asset overview](https://developer.apple.com/app-store/asset-best-practices/)
and [creative asset specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/creative-assets-specifications).

Use an artwork file, video, or folder of source files. Creative export needs
ImageMagick for images and posters, plus FFmpeg and FFprobe for video.
Composed iPhone and iPad designs also need Apple Frames. Artwork, feature cards,
already framed images and videos do not. It runs locally and makes no network
requests.

| `--asset` | Image export | Video export |
| --- | --- | --- |
| `header` | 3840 × 1646 PNG | 3840 × 1646 MP4, 5–30 seconds |
| `search-results` | 3840 × 2560 PNG | 3840 × 2560 MP4, 5–30 seconds |
| `universal` | 5244 × 2950 PNG for header and search | Image only |
| `event-card` | 3840 × 2160 PNG | 3840 × 2160 MP4, 15–30 seconds |
| `event-detail` | 2160 × 3840 PNG | 2160 × 3840 MP4, 15–30 seconds |
| `creative-all` | All five image profiles | All four video profiles |

```bash
asc-screens artwork.png --asset universal
asc-screens ./artwork --asset creative-all --output-root asc_out
asc-screens recording.mov --asset header --asset-max-duration 10 --asset-poster-time 2
asc-screens recording.mov --asset search-results --asset-fps 60 --asset-fit cover
```

`contain` is the default fit: it preserves the full source and pads the canvas
with the first selected background colour. `cover` fills the canvas with a
centered crop. Neither stretches the source. Images export as opaque sRGB PNGs;
videos export as silent H.264 MP4s at 30 or 60 fps. Video sources shorter than
the placement minimum fail instead of being extended. `--asset-max-duration`
trims from the start; `--asset-poster-time` selects a frame in that exported clip.
Without a design recipe, source artwork supplies the composition and text;
screenshot caption templates apply to screenshot mode.
Portrait screenshots usually need a separate landscape composition for headers
and search assets: padding leaves a narrow screenshot, while a centered crop
can remove most of its interface. Validate the composition as well as dimensions.

Use `--locale en-GB` to label an export. JSON configuration accepts the same
options, with underscores for option names:

```json
{
  "source": "artwork.png",
  "output_root": "asc_out",
  "asset": "universal",
  "asset_fit": "contain",
  "locale": "en-GB"
}
```

Review `asc_creative_review.html` for images, video playback, and posters.
`asc_creative_review.json` records metadata; `asc_upload.json` contains explicit
creative asset entries for the upload handoff. Source files stay intact. Keep
each screenshot or creative run in its own output root because each run writes
the upload manifest for that run.

Validate an export with its intended profile:

```bash
asc-screens ./asc_out --asset universal --check
```

Creative checks inspect image dimensions and alpha channels, or probed video
dimensions, frame rate, and duration. Event media also has a 500 MB limit.
Inspect crops and placement previews before assigning assets. The local review
does not reproduce Apple's product-page preview or imply approval.

### Curated app campaigns

`asc-screens-campaign` reuses an editorial selection of each app's strongest
captures, copy, icon, and colours. The included
[`portfolio.curated.json`](examples/portfolio.curated.json) records the local
Nodex, Termex, Codexex, Tesatlas, and Tescam selections. Paths assume these app
checkouts sit beside `asc-screens`; change them for another machine.

```bash
asc-screens-campaign --config examples/portfolio.curated.json --list
asc-screens-campaign --config examples/portfolio.curated.json --output-root out/portfolio
asc-screens-campaign --config examples/portfolio.curated.json --app nodex --asset header
```

The default campaign exports header, search results, and universal images for
each lead. Supporting features can specify fewer profiles. `--asset` overrides
the saved profiles; `--asset creative-all` exports all five formats. Event
formats are available explicitly rather than assuming every feature is an event.
Generation runs locally and never uploads.

The campaign file stores each selected source and any deliberate crop as
`[x, y, width, height]` in auto-oriented source pixels. Source captures remain
intact. Each app has a base `design`; a feature can override its copy or media
treatment. Output includes a gallery, per-app `asc_upload.json`, and a receipt
with source provenance and a fingerprint of the recipe, selected images, icons,
and renderer code. Crop bounds and selected inputs are checked before rendering.

These are saved editorial choices, not an automatic image-ranking model. After
a new capture session, update the source paths and review that the selected
feature still proves the message. Adding an app means adding its identity and
feature selections to the same campaign; shared layout improvements apply to
every app on its next render. The
[`portfolio.review.json`](examples/portfolio.review.json) explains the choices,
search intent, rejected leads, and capture gaps. It contains no measured search
volume or conversion results.

Guided `asc-gen` offers the same asset profiles after the build/check choice.
Choose `screenshots` for the existing iPhone, iPad, and Mac workflow.

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

By default the fingerprint includes the `asc-screens` config, its `source`, and
its `copy_file`, `design_file`, and referenced icon when present. CI settings and
the shared renderer code always contribute, so a template improvement invalidates
previous completion markers. Set `design_inputs` to control the artwork paths or
glob patterns. The default upload mapping is `iphone` to `IPHONE_69` and `ipad` to
`IPAD_PRO_3GEN_129`; Mac is generated locally but has no default CI device mapping.
Use the `device_type_map` field for any upload mapping required by the external CLI.

Print the cache key without building or uploading:

```bash
asc-screens-ci --config .asc-screens-ci.json --fingerprint-only
```

Normal runs require an already authenticated `asc` installation and replace remote screenshot sets on a cache miss. Read the configuration, cache and CI integration details in [`docs/asc-upload-ci.md`](docs/asc-upload-ci.md).

Creative manifests upload to the app's Asset Library through `asc-screens-ci`.
An optional `creative_asset_target` assigns header/search assets to an existing
version, custom page, or optimization treatment. Without that setting, the
handoff uploads to the library only. Inspect commands without building,
authenticating, or uploading:

```bash
asc-screens-ci --config .asc-screens-ci.json --dry-run
```

The handoff is checked against `asc` 5.14.3. Screenshot replacement uses both
`--replace` and `--confirm` as required by that version. Library upload and
placement assignment are separate from submission and publication.

### Development

This project follows [Clean Development](https://github.com/magrathean-uk/clean-development): run installs, builds and tests through `clean-development run --session session-only -- <command>` so no tool state is created under `~`. See the Clean development section of [AGENTS.md](AGENTS.md).

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
