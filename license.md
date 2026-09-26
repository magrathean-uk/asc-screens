# Licensing

## Controlling grant

`asc-screens` is licensed under the [MIT License](./LICENSE). The unmodified root `LICENSE` file controls if this page conflicts with it.

The source notice identifies the project copyright as `Copyright (c) 2026 Magrathean UK Ltd.` This page explains the repository layout and does not change that notice or grant additional rights.

## Package and external tools

`pyproject.toml` declares the package license as `MIT` and declares no Python runtime dependencies. The build backend is setuptools.

Rendering and optional upload workflows call separately installed tools: ImageMagick (`magick`), Apple Frames (`frames`), FFmpeg for App Preview creation, and `asc` for upload. Those tools are not relicensed by this repository and remain subject to their own terms and notices.

See [TRADEMARKS.md](./TRADEMARKS.md) for name-use notices.
