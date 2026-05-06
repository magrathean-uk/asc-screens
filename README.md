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

