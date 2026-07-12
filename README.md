# asc-screens

CLI for making App Store Connect screenshots from raw device screenshots.

Built by [Magrathean UK](https://magrathean.uk).

## Use

```bash
asc-screens ./source
```

Validate existing screenshots only:

```bash
asc-screens --check ./asc_out
```

Build one locale with caption copy:

```bash
asc-screens ./source --template title-bottom --copy-file copy.json --locale en-GB
```

Build all locales from config:

```bash
asc-screens --config asc-screens.json
```

Upload from CI only when design inputs changed:

```bash
asc-screens-ci --config .asc-screens-ci.json
```

Guided mode:

```bash
./asc-gen.py
```

Installed command:

```bash
asc-gen
```

Input can be:

- nested `iphone/` and `ipad/` folders
- one mixed folder of screenshots

The tool detects device type from image size when folders are mixed. It accepts PNG,
JPG, JPEG, HEIC, HEIF, TIF, and TIFF.

## Output

The tool writes ASC-sized PNGs into:

- `asc_out/iphone`
- `asc_out/ipad`
- `asc_out/_framed`

When locale copy is enabled, output becomes:

- `asc_out/<locale>/iphone`
- `asc_out/<locale>/ipad`

Current default export lanes:

- iPhone latest: `1320x2868`
- iPad latest: `2064x2752`

Batch lane aliases:

- `--kind iphone`
- `--kind ipad`
- `--kind all`
- `--kind iphone-latest`
- `--kind ipad-latest`
- `--kind all-latest`

Template aliases:

- `--template plain`
- `--template title-top`
- `--template title-bottom`

## Background

At start, the CLI asks for background colors.

Accepts:

- one hex color like `#FF8800`
- two hex colors like `#FF8800,#0088FF`
- three hex colors like `#060914,#1A26FF,#20D7E8`

If you give one color, the tool generates a 3-color hue palette from it.
If you give two colors, the tool fills the middle stop.

## Versions

- `v2.1.1`: agent guide and repo hygiene refresh
- `v1.0.0`: first CLI with device detection and framed ASC output
- `v2.0.0`: background flow supports 1 to 3 colors
- `v2.1.0`: guided CLI, recursive input, broader screenshot support

Unreleased:

- Current iPhone export now targets the latest accepted App Store lane.
- Built-in validation checks size, format, and PNG transparency.
- `--check` validates existing screenshots without framing them.
- Guided mode can run build or check flows.
- Latest-lane aliases work in guided and direct CLI flows.
- JSON config mode supports repeatable local and CI runs.
- Review and upload manifests are written after successful builds.
- Optional locale copy files drive multi-locale output and upload grouping.
- Optional top and bottom text templates can add safe background captions.
- `asc-screens-ci` can fingerprint design inputs, skip repeated uploads, and call the external `asc` CLI.

## Requirements

- ImageMagick `magick`
- Apple Frames CLI `frames`

## Validation

Built-in validation accepts App Store screenshot outputs for:

- iPhone: `1242x2688`, `1284x2778`, `1290x2796`, `1320x2868`
- iPad: `1488x2266`, `1668x2420`, `2048x2732`, `2064x2752`

Rules:

- format must be PNG, JPG, or JPEG
- PNG outputs must not have transparency
- size must match an accepted App Store lane for the device family

## Config

Example config:

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

## Localisation

Copy files are JSON:

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

Rules:

- titles and subtitles are optional
- `plain` template ignores copy text
- `title-top` and `title-bottom` place text on the background, not on the Apple frame
- if no copy file is supplied, `title-top` and `title-bottom` use the source filename as the title and strip a trailing `-ipad` or `-iphone`

## Manifests

Successful builds write:

- `asc_review.json` for operator review order
- `asc_review.html` for visual contact-sheet review
- `asc_upload.json` for `asc-cli` or other upload tooling handoff

## CI Upload

`asc-screens-ci` is for app repos that want screenshot uploads on `main` only
when design inputs changed. It keeps this tool local-only for asset generation
and uses the external `asc` CLI for App Store Connect.

Minimal `.asc-screens-ci.json`:

```json
{
  "app_id": "123456789",
  "version": "1.2.3",
  "asc_screens_config": "asc-screens.json",
  "output_root": "asc_out"
}
```

Default device mapping:

- `iphone`: `IPHONE_69`
- `ipad`: `IPAD_PRO_3GEN_129`

See [`docs/asc-upload-ci.md`](./docs/asc-upload-ci.md) for the GitHub Actions workflow.

## Install

```bash
python -m pip install -e .
```

## Legal

Copyright © 2026 Magrathean UK Ltd. asc-screens is licensed under the **MIT Licence**; see [`LICENSE`](./LICENSE) for the full text. The MIT Licence permits commercial and non-commercial use, modification, and redistribution, provided the copyright notice and the permission notice are retained in all copies or substantial portions.

### Trademarks and disclaimers

App Store, App Store Connect, Apple, the Apple logo, iPhone, and iPad are trademarks of Apple Inc. ImageMagick is a trademark of ImageMagick Studio LLC. asc-screens is **not affiliated with, endorsed by, sponsored by, or in any way officially connected to** Apple Inc., the Apple Frames CLI, ImageMagick Studio LLC, or `appshots`. References to these names exist solely for descriptive interoperability.

For commercial enquiries, email <contact@magrathean.uk>.

---

Magrathean UK Ltd. is a company registered in England and Wales (Company No. 16955343) with registered office at 16 Caledonian Court West Street, Watford, England, WD17 1RY.
