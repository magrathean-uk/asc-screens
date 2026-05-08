# asc-screens

CLI for making App Store Connect screenshots from raw device screenshots.

Built by [Magrathean UK](https://magrathean.uk).

## Use

```bash
asc-screens ./source
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

## Requirements

- ImageMagick `magick`
- Apple Frames CLI `frames`
- optional `npx appshots` for validation

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