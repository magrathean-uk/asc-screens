# asc-screens

Complete authorized changes and necessary safe local setup through the relevant checks. Use bounded delegation for independent work when useful, with clear file ownership. Do not ask again for actions already authorized by the task.

## Working boundaries

- Keep the command-line workflow local. Do not add telemetry or network calls to screenshot generation, validation, framing, or preview creation.
- `asc-screens-ci` is the only upload handoff. It invokes the external `asc` CLI and uses `--replace`; run replacement uploads only within the authorized target and scope. Ask if that authority or target is missing.
- Keep changes scoped to this repository and preserve unrelated dirty work.
- Preserve local source captures. Generated output, frame intermediates, review manifests, preview files, and `.asc-screens-cache/` stay out of Git.
- Keep iPhone, iPad, and Mac support aligned in direct and guided flows. Caption templates apply to framed iPhone and iPad output; Mac screenshots scale without framing or text.
- The CI default device map covers iPhone and iPad only. A Mac upload needs an explicit supported device mapping before it can use the upload handoff.

## Code map

- `asc_screens.py` discovers images, builds screenshots and previews, validates output, and writes review and upload manifests.
- `asc_gen.py` is the interactive wrapper. `asc-gen.py` and `asc_frame_maker.py` are entry-point shims.
- `asc_screens_ci.py` fingerprints declared design inputs and delegates authenticated upload to `asc`.
- `pyproject.toml` defines the package metadata and the `asc-screens`, `asc-gen`, and `asc-screens-ci` commands.

## Dependencies and checks

Use ImageMagick for validation and rendering, Apple Frames for device framing, and FFmpeg for `--preview`. The optional upload handoff also needs `asc` and its separately configured authentication.

```bash
python3 -m py_compile asc_screens.py asc_frame_maker.py asc_gen.py asc_screens_ci.py
python3 -m unittest discover -v
```

For a focused image check, use `asc-screens --check ./existing-screenshots` after installing the package, or run `python3 asc_screens.py --check ./existing-screenshots`. Discovery excludes every path containing `asc_out` or `_framed`, including in check mode. Use a separate copy of output when checking exports. Run the relevant test module first; commands and manual acceptance checks are in `CONTRIBUTING.md`. A render or upload is a separate acceptance step that needs representative inputs and the relevant external tools or account access.

Read `README.md` before changing the user workflow and `docs/asc-upload-ci.md` before changing the upload handoff.
