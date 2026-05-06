# AGENTS.md

Read [README](./README.md) first.

## Scope

- Work only inside this repo.
- Keep the CLI prompt-driven and local-only.
- Keep generated screenshot output out of git.

## Commands

```bash
python -m pip install -e .
asc-screens ./source
./asc-gen.py
```

## Source of truth

- `asc_screens.py` owns screenshot discovery, sizing, palette expansion, and export.
- `asc-gen.py` is the guided local wrapper.
- `pyproject.toml` owns package metadata and console entry points.

## Repo rules

- Accept mixed iPhone and iPad inputs.
- Detect device type from image size when folders are mixed.
- Treat `asc_out/`, framed output folders, preview images, and tool caches as generated.
- Do not add telemetry or network calls.
