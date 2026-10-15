# Contributing

Keep changes focused on screenshot generation, validation, guided input or the
explicit upload handoff. Read the [README](../README.md) for user flows and
[AGENTS.md](../AGENTS.md) for the source map and project boundaries.

## Local setup

Use Python 3.11 or later. From a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
clean-development run --session session-only -- python3 -m pip install -e .
```

Do not commit the virtual environment or generated package metadata. Install
external rendering tools separately as described in the README. The unit tests
use the Python standard library and mock rendering and upload commands.

This project follows
[Clean Development](https://github.com/magrathean-uk/clean-development):
installs, builds and tests run through
`clean-development run --session session-only -- <command>`, and no tool state
is created under `~`. The commands below are shown without that wrapper for
brevity. See the Clean development section of [AGENTS.md](../AGENTS.md).

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
| Creative design, icon palettes, gradient finishes, device frames, media generation and validation | `python3 -m unittest test_asc_design test_asc_icon_palette test_asc_finish test_asc_device_frames test_asc_creative test_asc_asset_cli -v` |
| Curated per-app campaigns and crop provenance | `python3 -m unittest test_asc_campaign -v` |

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

For composed creatives, inspect wide and portrait exports with representative
local app icons. The studio background should be a smooth full-canvas gradient
using the icon's visible colours, quiet beside the copy and richer behind the
product. It must not add panels, outlines, motifs, or accent rules. Check that
`flat` is uniform and that changing an icon changes the gradient and its
fingerprint. Use a local frame pack through `FRAMES_ASSETS` or a recipe path such
as `"frame_assets": "$BOLYKI_DEV_LIBS/frames-apple401"`; environment variables
and `~` expand before resolving the path. Confirm real device cutouts and
outlines remain intact after rendering.

For CI changes, use mocked commands to verify the handoff. A live run replaces
remote screenshots and requires an intended target and explicit authorization.
Read the [upload guide](../docs/asc-upload-ci.md) before operating it.

## Submitting a change

Explain the problem, the resulting behavior and the checks you ran. Add a focused
regression test when behavior changes. Call out any checks you could not run and
any external tool versions relevant to the result. Keep unrelated work intact.
Use synthetic or redacted images in reproductions; omit credentials and account
data. Send vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue.

Preserve the [MIT license](../LICENSE), copyright notices and third-party attribution.
Only submit code and assets you have permission to share. See the
[licensing notes](../docs/legal/third-party-notices.md) for the boundary between this code and external tools.
