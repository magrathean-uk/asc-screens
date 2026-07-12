# AGENTS.md

Read `README.md` and `docs/asc-upload-ci.md` before changing the related flow.

## Scope

- Work only inside this repo.
- Keep the CLI prompt-driven and local-only.
- Keep generated screenshot output out of git.

## Commands

```bash
python3 -m pip install -e .
python3 -m unittest discover -v
asc-screens ./source
asc-gen
```

## Source of truth

- `asc_screens.py` owns screenshot discovery, sizing, palette expansion, and export.
- `asc_gen.py` owns the guided local wrapper; `asc-gen.py` is its script shim.
- `asc_screens_ci.py` owns design-input fingerprinting and `asc` upload handoff.
- `pyproject.toml` owns package metadata and console entry points.

## Repo rules

- Accept mixed iPhone and iPad inputs.
- Detect device type from image size when folders are mixed.
- Treat `asc_out/`, framed output folders, preview images, and tool caches as generated.
- Keep framing local and add no telemetry. Network access belongs only to the
  explicit `asc-screens-ci` upload handoff.
- Preserve unrelated dirty work and report any skipped verification.
