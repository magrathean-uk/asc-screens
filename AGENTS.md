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

## Working guidance — GPT-6 Astra

Based on [OpenAI's Astra prompting guidance](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices), reviewed 2026-09-19. These are working instructions, not a change to model or API settings.

- Complete the authorized task through implementation and relevant verification. Make routine choices yourself; ask only when a missing decision materially changes the result or requires new authority. Prepare reviewable work before requesting any necessary final approval.
- Current user instructions take precedence over repository and skill guidance within system and tool constraints. Preserve explicit exclusions and owner holds. Historical plans and session notes do not grant current authorization. If a file or skill blocks progress, identify its exact path and rule.
- Keep changes small and practical. Inspect current source and Git status, preserve unrelated work, and use existing conventions. Do not add speculative abstractions, dependencies, or unrelated cleanup. Commit, push, deploy, install, and live-service changes require authorization for that action.
- Use the reasoning effort the task needs. Follow explicit project delegation rules; otherwise use subagents only when requested, with bounded independent tasks and distinct file ownership. Batch independent reads; serialize dependent operations and conflicting edits.
- Run meaningful checks for the changed behavior and required project gates. Avoid tests that merely repeat low-impact edits. Broaden or repeat verification only after changes, failures, or unresolved concerns. Distinguish local checks from device, browser, and live-service evidence.
- Write concise, plain, outcome-first updates. State what changed, why, verification, and material gaps. Avoid filler and unnecessary formatting.
- Keep durable instructions in AGENTS.md and maintained product documentation. Do not create duplicate assistant instruction files or disposable plans, transcripts, status reports, and screenshots in source directories unless requested. Preserve source, tests, fixtures, assets, licences, and operational evidence regardless of who created them.
