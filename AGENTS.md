# asc-screens

This file provides project context and command references.

asc-screens is a local command-line workflow that generates, validates, frames and uploads App Store Connect screenshots. Screenshot generation, validation, framing and preview creation run locally. Uploads use the external `asc` CLI through `asc-screens-ci`, with `--replace` and separately configured account authentication.

## Code map

- `asc_screens.py` discovers images, builds screenshots and previews, validates output, and writes review and upload manifests.
- `asc_gen.py` is the interactive wrapper. `asc-gen.py` and `asc_frame_maker.py` are entry-point shims.
- `asc_screens_ci.py` fingerprints declared design inputs and delegates authenticated upload to `asc`.
- `pyproject.toml` defines the package metadata and the `asc-screens`, `asc-gen`, and `asc-screens-ci` commands.

## Device and output behaviour

The direct and guided flows support iPhone, iPad and Mac. Caption templates apply to framed iPhone and iPad output; Mac screenshots scale without framing or text. The CI default device map covers iPhone and iPad; Mac upload support depends on a supported device mapping.

Generated artefacts include output screenshots, frame intermediates, review manifests, preview files and `.asc-screens-cache/`. Image discovery excludes paths containing `asc_out` or `_framed`, including in check mode, so export checks can use a separate output copy.

## Dependencies and command references

ImageMagick supplies validation and rendering, Apple Frames supplies device framing, and FFmpeg supports `--preview`. The upload handoff also depends on `asc` and account access.

```bash
python3 -m py_compile asc_screens.py asc_frame_maker.py asc_gen.py asc_screens_ci.py
python3 -m unittest discover -v
asc-screens --check ./existing-screenshots
python3 asc_screens.py --check ./existing-screenshots
```

`.github/CONTRIBUTING.md` describes commands and manual acceptance checks. Rendering and uploading have additional input, external-tool and account dependencies beyond the local Python checks. `README.md` describes the user workflow; `docs/asc-upload-ci.md` describes the upload handoff.
