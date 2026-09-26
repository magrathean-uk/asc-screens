# Contributing

Keep changes focused on screenshot generation, validation, guided input or the
explicit upload handoff. Read the [README](README.md) for user flows and
[AGENTS.md](AGENTS.md) for the source map and project boundaries.

## Local setup

Use Python 3.10 or later. From a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

Do not commit the virtual environment or generated package metadata. Install
external rendering tools separately as described in the README. The unit tests
use the Python standard library and mock rendering and upload commands.

For optional cache management, consider
[Clean Development](https://github.com/magrathean-uk/clean-development).
It is not required to contribute.

## Verification

Run the unit suite from the repository root:

```bash
python3 -m unittest discover -v
```

For a focused change, start with its test module:

| Area | Command |
| --- | --- |
| Rendering, sizing, validation, manifests and previews | `python3 -m unittest test_asc_frame_maker -v` |
| Guided input choices | `python3 -m unittest test_asc_gen_cli -v` |
| Fingerprinting and upload command construction | `python3 -m unittest test_asc_screens_ci -v` |

Check parser entry points without rendering:

```bash
python3 asc_screens.py --help
python3 asc_screens_ci.py --help
```

`asc-gen` is interactive and has no `--help` parser. Check guided changes with
representative input and the prompts. Rendering changes need a real local run
with ImageMagick and Apple Frames CLI, followed by inspection of images, captions,
output counts and the contact sheet. Preview changes also need FFmpeg and playback
of the result. Unit tests alone do not prove visual quality or App Store acceptance.

For CI changes, use mocked commands to verify the handoff. A live run replaces
remote screenshots and requires an intended target and explicit authorization.
Read the [upload guide](docs/asc-upload-ci.md) before operating it.

## Submitting a change

Explain the problem, the resulting behavior and the checks you ran. Add a focused
regression test when behavior changes. Call out any checks you could not run and
any external tool versions relevant to the result. Keep unrelated work intact.
Use synthetic or redacted images in reproductions; omit credentials and account
data. Send vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue.

Preserve the [MIT license](LICENSE), copyright notices and third-party attribution.
Only submit code and assets you have permission to share. See the
[licensing notes](license.md) for the boundary between this code and external tools.
