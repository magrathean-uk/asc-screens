# asc-screens

CLI for making App Store Connect screenshots from raw device screenshots.

## Use

```bash
asc-screens ./source
```

Input can be:

- `./source/iphone/*.png` and `./source/ipad/*.png`
- one mixed folder of PNGs

The tool detects device type from image size when folders are mixed.

## Output

The tool writes ASC-sized PNGs into:

- `asc_out/iphone`
- `asc_out/ipad`
- `asc_out/_framed`

## Background

At start, the CLI asks for background colors.

Accepts:

- one hex color like `#FF8800`
- three hex colors like `#060914,#1A26FF,#20D7E8`

If you give one color, the tool generates a 3-color hue palette from it.

## Requirements

- ImageMagick `magick`
- Apple Frames CLI `frames`
- optional `npx appshots` for validation

## Install

```bash
python -m pip install -e .
```

