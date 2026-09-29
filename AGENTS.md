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

For a focused image check, use `asc-screens --check ./existing-screenshots` after installing the package, or run `python3 asc_screens.py --check ./existing-screenshots`. Discovery excludes every path containing `asc_out` or `_framed`, including in check mode. Use a separate copy of output when checking exports. Run the relevant test module first; commands and manual acceptance checks are in `.github/CONTRIBUTING.md`. A render or upload is a separate acceptance step that needs representative inputs and the relevant external tools or account access.

Read `README.md` before changing the user workflow and `docs/asc-upload-ci.md` before changing the upload handoff.

<!-- clean-development-policy:v1 (canonical text: ~/dev/source/dev-bootstrap/snippets/clean-development-policy.md) -->
## Clean development (mandatory)

This project follows [Clean Development](https://github.com/magrathean-uk/clean-development) and the machine rule that nothing creates tool state under `~` (only the allow-listed agent homes).

- The shell environment comes from `~/.zshenv`, which loads `~/dev/env.zsh`. It routes every tool home and cache (`CARGO_HOME`, `RUSTUP_HOME`, `XDG_*`, `BUNDLE_USER_HOME`, `npm_config_cache`, `XCODE_DERIVED_DATA_PATH`, ...) and switches telemetry off. Never unset, override or bypass those variables. If a script needs a scrubbed environment, re-export them with `source ~/dev/env.zsh`.
- Run builds, tests, installs and anything else that writes caches or build output through Clean Development: `clean-development run --session session-only -- <command>`. Follow its docs and keep its receipts.
- Do not add installers or scripts that default into `~` (`~/.cargo`, `~/.rustup`, `~/.cache`, `~/.npm`, `~/.swiftpm`, `~/.gradle`, ...) and do not hardcode `$HOME` paths for caches; use the routed variables.
- Before finishing, run `dev-env-check` (must pass) and `dev-audit` (no new entries in `~`). If your work caused a violation, fix the cause in the repo and say so.

## Legal files

Legal files (`LICENSE`, `NOTICE`, `docs/legal/`, contributor terms, copyright and attribution strings) are owner-controlled: change them only on the owner's explicit instruction.
