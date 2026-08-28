# asc-screens

Prompt-driven CLI for turning raw iPhone and iPad captures into validated App Store Connect screenshot sets.

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

Guided mode from a checkout:

```bash
./asc-gen.py
```

Installed command:

```bash
asc-gen
```

Input can be a nested `iphone/` and `ipad/` directory layout or one mixed folder. Device type is detected from image dimensions when inputs are mixed. Supported source formats are PNG, JPG, JPEG, HEIC, HEIF, TIF, and TIFF.

## Output

The default output layout is:

- `asc_out/iphone`
- `asc_out/ipad`
- `asc_out/_framed`

When locale copy is enabled:

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

At startup, the interactive CLI asks for background colours.

Accepted forms:

- one hex colour, such as `#FF8800`;
- two hex colours, such as `#FF8800,#0088FF`;
- three hex colours, such as `#060914,#1A26FF,#20D7E8`.

One colour expands into a three-stop hue palette. Two colours generate the middle stop automatically.

## Requirements

- Python 3.10 or later.
- ImageMagick `magick`.
- Apple Frames CLI `frames`.

Install the Python package from a checkout:

```bash
python3 -m pip install -e .
```

External tools must be installed separately and available on `PATH`.

## Validation

Built-in validation accepts App Store screenshot outputs for:

- iPhone: `1242x2688`, `1284x2778`, `1290x2796`, `1320x2868`;
- iPad: `1488x2266`, `1668x2420`, `2048x2732`, `2064x2752`.

Rules:

- format must be PNG, JPG, or JPEG;
- PNG outputs must not contain transparency;
- dimensions must match an accepted App Store lane for the device family.

## Config

Example:

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

- titles and subtitles are optional;
- `plain` ignores copy text;
- `title-top` and `title-bottom` place text on the background, not on the Apple frame;
- without a copy file, caption templates use the source filename as the title and strip a trailing `-ipad` or `-iphone`.

## Manifests

Successful builds write:

- `asc_review.json` — operator review order;
- `asc_review.html` — visual contact-sheet review;
- `asc_upload.json` — handoff for `asc-cli` or another upload tool.

## CI upload

`asc-screens-ci` supports app repositories that should upload screenshots from `main` only when design inputs changed. Asset generation remains local; upload is delegated to the external `asc` CLI.

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

## Development verification

```bash
python3 -m py_compile asc_screens.py asc_frame_maker.py asc_gen.py asc_screens_ci.py
asc-screens --help
asc-gen --help
asc-screens-ci --help
```

A full render also requires representative source screenshots plus working `magick` and `frames` commands.

## Releases

- `v1.0.0` — first CLI with device detection and framed App Store output.
- `v2.0.0` — one-to-three-colour background workflow.
- `v2.1.0` — guided CLI, recursive input, and broader source format support.
- `v2.1.1` — agent guide and repository hygiene refresh.

See [`RELEASES.md`](./RELEASES.md) for the current unreleased change set and full release notes.

## Legal

Copyright © 2026 Magrathean UK Ltd. `asc-screens` is licensed under the [MIT Licence](./LICENSE). Report security issues through [`SECURITY.md`](./SECURITY.md).

App Store, App Store Connect, Apple, the Apple logo, iPhone, and iPad are trademarks of Apple Inc. ImageMagick is a trademark of ImageMagick Studio LLC. `asc-screens` is not affiliated with, endorsed by, sponsored by, or officially connected to Apple Inc., the Apple Frames CLI, ImageMagick Studio LLC, or `appshots`. References to these names exist solely for descriptive interoperability. See [`TRADEMARKS.md`](./TRADEMARKS.md).

For commercial enquiries, email <contact@magrathean.uk>.

---

Magrathean UK Ltd. is a company registered in England and Wales (Company No. 16955343) with registered office at 16 Caledonian Court West Street, Watford, England, WD17 1RY.
