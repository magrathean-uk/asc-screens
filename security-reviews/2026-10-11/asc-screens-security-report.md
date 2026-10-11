# Security Review: asc-screens

## Scope

Offline Standard audit of all 26 Git-tracked asc-screens files, focused on renderer outputs, review HTML, and CI App Store upload boundaries.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_dd8fe3740e8251a9c149f90215eb052d77470a39d1e429b1269e99d0e70cd972
- Revision: d7aa4647e21b308130d03a81319948f896606aa7
- Snapshot digest: codex-security-snapshot/v1:sha256:113d20a3da0637a83af9705967b1b51bcfe14e3775ac6ac4331b1a42b847ca7f
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Artifacts reviewed: asc_screens.py, asc_gen.py, asc_screens_ci.py, asc_frame_maker.py, asc-gen.py, pyproject.toml, .github/workflows/dependency-audit.yml, .github/SECURITY.md, source tests, README and CI upload guide

Limitations and exclusions:
- External Apple Frames, ImageMagick, FFmpeg and asc CLI implementations were not assessed.
- No live App Store Connect calls, media build, browser execution, or upload occurred.
- Excluded docs/legal/\*\*, CHANGELOG.md, LICENSE: Non-executable legal and release prose inventoried; no runtime security boundary.
- Excluded AGENTS.md, CLAUDE.md: Local agent guidance inspected as repository data only; user revoked it as instructions for this audit.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 3 |
| Severity mix | medium: 2, low: 1 |
| Confidence mix | high: 2, medium: 1 |
| Coverage | complete |
| Validation mode | static |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Local screenshot renderer/validator writes images, HTML review sheet and manifests; optional CI wrapper fingerprints inputs then invokes separately authenticated `asc` CLI to replace screenshots in an existing App Store version/localization (README.md:13-25,129-165; asc_screens_ci.py:94-133,162-205).

### Assets

- Private source captures, locale copy, generated screenshots/contact sheet/manifests (asc_screens.py:714-738,741-775; README.md:129-151)
- ASC app/version/localization identifiers and separately configured CLI credentials (asc_screens_ci.py:112-133,162-193; docs/asc-upload-ci.md:10-15)
- Local cache marker controlling whether a replacement upload is skipped (asc_screens_ci.py:196-205)

### Trust Boundaries

- Untrusted local image/copy/config -\> ImageMagick, Apple Frames, ffmpeg subprocesses and local outputs (asc_screens.py:106-125,153-161,793-875)
- Generated asc_upload.json + CI config -\> external asc auth/list/localization lookup -\> per-family directory screenshots upload --replace remote write (asc_screens_ci.py:112-133,162-193)
- CI design-input files/globs -\> SHA-256 cache key -\> local .done marker; branch/credentials/event authorization belong to external workflow (asc_screens_ci.py:60-109,196-205; docs/asc-upload-ci.md:7-8,98-113)
- Locale copy and source-derived filenames become filesystem path segments and raw HTML contact-sheet content (asc_screens.py:577-585,612-621,741-777,861-874).

### Attacker Capabilities

- A caller able to edit CI config, design inputs, or output manifest can steer app/version, locale/family mapping and local upload directories, subject to separately configured ASC credentials and external CLI behavior (asc_screens_ci.py:112-133,162-193)
- A local content supplier can provide images, copy, and filenames consumed by external media tools and rendered into artifacts; this is a trust boundary, not a validated finding (asc_screens.py:153-161,637-682,793-875)

### Security Objectives

- Prevent unintended replacement by scoping app/version/localization and running upload only with authorized CI event/credentials (docs/asc-upload-ci.md:3-20,98-113)
- Keep local screenshots/private content out of public logs and artifacts; review actual output before upload (docs/asc-upload-ci.md:17-20,113-114)
- Make cache marker reflect only completed command sequence, and understand it does not prove remote state (asc_screens_ci.py:196-205; docs/asc-upload-ci.md:88-96)

### Assumptions

- The external asc executable owns authentication, ASC API transport, and --replace semantics; no credentials or live API were inspected (asc_screens_ci.py:162-193; docs/asc-upload-ci.md:116-132).
- The renderer does not clear stale images, and uploader passes whole directories, not manifest filenames; effective upload set may exceed newly rendered entries (README.md:151; docs/asc-upload-ci.md:17-20; asc_screens_ci.py:176-193).
- No repository workflow itself establishes branch/event gate; external app CI integration is prerequisite (docs/asc-upload-ci.md:7-8,98-113).
- The tracked dependency-audit workflow does not run the upload handoff; consuming app CI must establish event/branch authorization (.github/workflows/dependency-audit.yml:1-27; docs/asc-upload-ci.md:98-113).

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [CI can upload stale screenshots omitted from the current manifest](#finding-1) | medium | medium | inline below |
| [Locale names can redirect screenshot writes outside the selected output folder](#finding-2) | medium | high | inline below |
| [Unescaped screenshot names and locales can run script in the review sheet](#finding-3) | low | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] CI can upload stale screenshots omitted from the current manifest

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | The source and docs show whole-directory handoff and no cleanup; exact remote acceptance and final file set depend on the external asc CLI, which was not run. |
| Category | Unintended data upload from stale build output |
| CWE | CWE-200 |
| Affected lines | asc_screens.py:395, asc_screens.py:719, asc_screens_ci.py:183, asc_screens_ci.py:191 |

#### Summary

The renderer leaves prior images in output directories, while the CI uploader ignores the manifest's per-file entries and asks the external asc CLI to upload each whole family directory with --replace. A stale PNG can therefore join an authorized remote replacement upload.

#### Root Cause

The upload boundary trusts an output directory whose contents are not reconciled to the current generated manifest.

**Renderer reuses existing folder** — `asc_screens.py:395-397`

The output folder is reused and the renderer does not remove files no longer in the current input set.

```python
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for_source(output_dir, source)
    run(
```

**Manifest derived from current outputs** — `asc_screens.py:714-731`

Manifest entries only describe images produced this run, not old files already present in a selected folder.

```python
def write_upload_manifest(output_root, outputs):
    if not outputs:
        return None
    root = Path(output_root)
    payload = {"locales": {}}
    for path in sorted((Path(path) for path in outputs)):
        relative = path.relative_to(root)
        if len(relative.parts) == 3:
            locale, family, filename = relative.parts
        elif len(relative.parts) == 2:
            family, filename = relative.parts
            locale = "default"
        else:
            raise ValueError(f"Unexpected output path: {path}")
        family_bucket = payload["locales"].setdefault(locale, {}).setdefault(family, [])
        family_bucket.append(
```

**Uploader passes entire family directory** — `asc_screens_ci.py:176-193`

The manifest's filename and path fields are unused; the external CLI receives a whole directory for a remote replacement.

```python
        for family in sorted(families):
            device_type = config.device_type_map[family]
            screenshot_dir = config.output_root / locale / family if locale != "default" else config.output_root / family
            run_command(
                [
                    asc_bin,
                    "screenshots",
                    "upload",
                    "--version-localization",
                    localization_id,
                    "--path",
                    str(screenshot_dir),
                    "--device-type",
                    device_type,
                    "--replace",
                ],
                runner=runner,
            )
```

#### Validation

Fresh manifest item lists do not constrain the file set passed to asc; the wrapper hands off the existing directory to --replace without clearing or comparing contents.

Validation method: Static renderer-to-CLI handoff trace

**Renderer reuses existing folder** — `asc_screens.py:395-397`

The output folder is reused and the renderer does not remove files no longer in the current input set.

```python
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for_source(output_dir, source)
    run(
```

**Manifest derived from current outputs** — `asc_screens.py:714-731`

Manifest entries only describe images produced this run, not old files already present in a selected folder.

```python
def write_upload_manifest(output_root, outputs):
    if not outputs:
        return None
    root = Path(output_root)
    payload = {"locales": {}}
    for path in sorted((Path(path) for path in outputs)):
        relative = path.relative_to(root)
        if len(relative.parts) == 3:
            locale, family, filename = relative.parts
        elif len(relative.parts) == 2:
            family, filename = relative.parts
            locale = "default"
        else:
            raise ValueError(f"Unexpected output path: {path}")
        family_bucket = payload["locales"].setdefault(locale, {}).setdefault(family, [])
        family_bucket.append(
```

**Uploader passes entire family directory** — `asc_screens_ci.py:176-193`

The manifest's filename and path fields are unused; the external CLI receives a whole directory for a remote replacement.

```python
        for family in sorted(families):
            device_type = config.device_type_map[family]
            screenshot_dir = config.output_root / locale / family if locale != "default" else config.output_root / family
            run_command(
                [
                    asc_bin,
                    "screenshots",
                    "upload",
                    "--version-localization",
                    localization_id,
                    "--path",
                    str(screenshot_dir),
                    "--device-type",
                    device_type,
                    "--replace",
                ],
                runner=runner,
            )
```

**Documentation acknowledges stale uploads** — `docs/asc-upload-ci.md:17-20`

The documented warning confirms the behavior but does not enforce a safe upload set.

```markdown
First build locally with `asc-screens --config asc-screens.json` and inspect the
images, output count and `asc_review.html`. Use a fresh output directory when
changing input sets: the renderer does not remove stale images, and the uploader
passes whole directories to `asc`, rather than individual manifest entries.
```

Counterevidence and remaining uncertainty:
- The docs warn users to choose a fresh output directory when input sets change.
- An authorized ASC account and an actual stale eligible file are required.
- The external asc CLI's exact filtering and remote acceptance were not tested.

Limitations:
- No live ASC account, remote replacement, or filesystem artifact was exercised.

#### Dataflow

Old file persists -\> manifest lists only new outputs -\> uploader selects family directory, not file list

- **Source:** Stale output-directory file

- **Sink:** External asc screenshots upload --path directory --replace

- **Outcome:** Unintended remote screenshot publication

**Renderer reuses existing folder** — `asc_screens.py:395-397`

The output folder is reused and the renderer does not remove files no longer in the current input set.

```python
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for_source(output_dir, source)
    run(
```

**Manifest derived from current outputs** — `asc_screens.py:714-731`

Manifest entries only describe images produced this run, not old files already present in a selected folder.

```python
def write_upload_manifest(output_root, outputs):
    if not outputs:
        return None
    root = Path(output_root)
    payload = {"locales": {}}
    for path in sorted((Path(path) for path in outputs)):
        relative = path.relative_to(root)
        if len(relative.parts) == 3:
            locale, family, filename = relative.parts
        elif len(relative.parts) == 2:
            family, filename = relative.parts
            locale = "default"
        else:
            raise ValueError(f"Unexpected output path: {path}")
        family_bucket = payload["locales"].setdefault(locale, {}).setdefault(family, [])
        family_bucket.append(
```

**Uploader passes entire family directory** — `asc_screens_ci.py:176-193`

The manifest's filename and path fields are unused; the external CLI receives a whole directory for a remote replacement.

```python
        for family in sorted(families):
            device_type = config.device_type_map[family]
            screenshot_dir = config.output_root / locale / family if locale != "default" else config.output_root / family
            run_command(
                [
                    asc_bin,
                    "screenshots",
                    "upload",
                    "--version-localization",
                    localization_id,
                    "--path",
                    str(screenshot_dir),
                    "--device-type",
                    device_type,
                    "--replace",
                ],
                runner=runner,
            )
```

#### Reachability

Unreconciled local artifact crosses into production upload scope.

- **Attacker:** Prior artifact producer or process with write access to the configured output directory

- **Entry point:** Preexisting screenshot in output_root/\<locale\>/\<family\>

- **Outcome:** Old/unreviewed image may be included in the remote replacement set.

Preconditions:
- CI cache miss or --force initiates an authorized upload.
- A stale eligible image remains in the family directory.

Limitations:
- Remote acceptance depends on the external asc implementation and App Store rules.

#### Severity

**Medium** — Unintended screenshot publication can expose older/private imagery or replace the intended App Store set. It requires an authorized CI upload and a preexisting eligible file in the output directory; the risk is documented but not enforced away.

Higher if output directories or caches are writable by less-trusted jobs or if private screenshots coexist with production output.

#### Remediation

Upload only a fresh, staged directory containing files enumerated by the current manifest; verify exact names and hashes before --replace, or refuse upload when a selected family directory contains extras.

Tests:
- A stale PNG outside the manifest is rejected or excluded before the asc command is invoked.
- Upload still includes every newly generated manifest entry in intended slot order.
- CI cache miss with a reused output directory cannot silently publish old files.

<a id="finding-2"></a>

### [2] Locale names can redirect screenshot writes outside the selected output folder

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The JSON-to-path-to-write trace is direct in both CLIs; no runtime reproduction was performed. |
| Category | Path traversal in locale-derived output directory |
| CWE | CWE-22 |
| Affected lines | asc_screens.py:580, asc_screens.py:865, asc_screens.py:395, asc_gen.py:151 |

#### Summary

Locale keys from the operator-selected copy JSON are used directly as path components. A `..` or absolute locale can cause framed and rendered images to be written outside output_root before the post-build manifest step.

#### Root Cause

The locale is treated as a trusted filesystem path segment despite originating in content data.

**Copy file keys accepted unchanged** — `asc_screens.py:577-585`

Locale keys remain arbitrary strings from the copy file.

```python
def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
    }
```

**Locale becomes output root** — `asc_screens.py:863-870`

`Path` joining allows `..` components and absolute right-hand paths, with no resolved containment test.

```python
    localized_builds = resolve_localized_builds(args.copy_file, args.locale)
    for build_locale, copy in localized_builds:
        scoped_root = Path(args.output_root) / build_locale if build_locale else Path(args.output_root)
        scoped_args = argparse.Namespace(**vars(args))
        scoped_args.output_root = scoped_root
        for kind, target_size in expand_export_targets(args.kind):
            built = process_kind(scoped_args, jobs, kind, background_colors, target_size=target_size, template=args.template, copy=copy)
            outputs.extend(built)
```

**Renderer creates directory and writes PNG** — `asc_screens.py:395-423`

The locale-derived output directory is created and used as ImageMagick's destination before manifest generation.

```python
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for_source(output_dir, source)
    run(
        [
            "magick",
            *background_command(target_w, target_h, background_colors),
            *overlay_text_command(target_w, target_h, template, copy),
            "(",
            str(framed),
            "-filter",
            "Lanczos",
            "-define",
            "filter:blur=0.9891028367558475",
            "-resize",
            f"{fit_w}x{fit_h}!",
            ")",
            "-gravity",
            "center",
            "-composite",
            "-alpha",
            "off",
            "-colorspace",
            "sRGB",
            "-depth",
            "8",
            "-type",
            "TrueColor",
            "-strip",
            f"PNG24:{output}",
```

#### Validation

No locale identifier or containment check occurs before the build path is passed to mkdir and ImageMagick; a manifest error, if any, occurs only after writes.

Validation method: Static source-to-sink trace

**Copy file keys accepted unchanged** — `asc_screens.py:577-585`

Locale keys remain arbitrary strings from the copy file.

```python
def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
    }
```

**Locale becomes output root** — `asc_screens.py:863-870`

`Path` joining allows `..` components and absolute right-hand paths, with no resolved containment test.

```python
    localized_builds = resolve_localized_builds(args.copy_file, args.locale)
    for build_locale, copy in localized_builds:
        scoped_root = Path(args.output_root) / build_locale if build_locale else Path(args.output_root)
        scoped_args = argparse.Namespace(**vars(args))
        scoped_args.output_root = scoped_root
        for kind, target_size in expand_export_targets(args.kind):
            built = process_kind(scoped_args, jobs, kind, background_colors, target_size=target_size, template=args.template, copy=copy)
            outputs.extend(built)
```

**Renderer creates directory and writes PNG** — `asc_screens.py:395-423`

The locale-derived output directory is created and used as ImageMagick's destination before manifest generation.

```python
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for_source(output_dir, source)
    run(
        [
            "magick",
            *background_command(target_w, target_h, background_colors),
            *overlay_text_command(target_w, target_h, template, copy),
            "(",
            str(framed),
            "-filter",
            "Lanczos",
            "-define",
            "filter:blur=0.9891028367558475",
            "-resize",
            f"{fit_w}x{fit_h}!",
            ")",
            "-gravity",
            "center",
            "-composite",
            "-alpha",
            "off",
            "-colorspace",
            "sRGB",
            "-depth",
            "8",
            "-type",
            "TrueColor",
            "-strip",
            f"PNG24:{output}",
```

**Guided mode repeats the join** — `asc_gen.py:150-156`

The interactive wrapper has the same locale path boundary.

```python
    for build_locale, copy in resolve_localized_builds(copy_file, locale):
        scoped_root = Path(output_root) / build_locale if build_locale else Path(output_root)
        scoped_args = Namespace(**vars(args))
        scoped_args.output_root = scoped_root
        for kind in kinds:
            for resolved_kind, target_size in expand_export_targets(kind):
                built = process_kind(scoped_args, jobs, resolved_kind, background_colors, target_size=target_size, template=template, copy=copy)
```

Counterevidence and remaining uncertainty:
- The operator must choose/configure the copy JSON; the direct JSON itself is not fetched by this tool.
- Generated output is PNG media with names derived from source stems, not arbitrary bytes.
- Subprocesses receive argument lists, not shell strings.

Limitations:
- No crafted locale or media build was executed.

#### Dataflow

locale -\> build_locale -\> scoped_root -\> output_dir -\> PNG24 path

- **Source:** Unvalidated JSON locale key

- **Sink:** mkdir and ImageMagick PNG24 output

- **Outcome:** Write outside configured output_root

**Copy file keys accepted unchanged** — `asc_screens.py:577-585`

Locale keys remain arbitrary strings from the copy file.

```python
def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
    }
```

**Locale becomes output root** — `asc_screens.py:863-870`

`Path` joining allows `..` components and absolute right-hand paths, with no resolved containment test.

```python
    localized_builds = resolve_localized_builds(args.copy_file, args.locale)
    for build_locale, copy in localized_builds:
        scoped_root = Path(args.output_root) / build_locale if build_locale else Path(args.output_root)
        scoped_args = argparse.Namespace(**vars(args))
        scoped_args.output_root = scoped_root
        for kind, target_size in expand_export_targets(args.kind):
            built = process_kind(scoped_args, jobs, kind, background_colors, target_size=target_size, template=args.template, copy=copy)
            outputs.extend(built)
```

**Renderer creates directory and writes PNG** — `asc_screens.py:395-423`

The locale-derived output directory is created and used as ImageMagick's destination before manifest generation.

```python
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for_source(output_dir, source)
    run(
        [
            "magick",
            *background_command(target_w, target_h, background_colors),
            *overlay_text_command(target_w, target_h, template, copy),
            "(",
            str(framed),
            "-filter",
            "Lanczos",
            "-define",
            "filter:blur=0.9891028367558475",
            "-resize",
            f"{fit_w}x{fit_h}!",
            ")",
            "-gravity",
            "center",
            "-composite",
            "-alpha",
            "off",
            "-colorspace",
            "sRGB",
            "-depth",
            "8",
            "-type",
            "TrueColor",
            "-strip",
            f"PNG24:{output}",
```

#### Reachability

Content metadata crosses into filesystem path selection.

- **Attacker:** Contributor of a copy JSON consumed by the operator/CI

- **Entry point:** Top-level locale key in copy JSON

- **Outcome:** Generated PNG or framed intermediary outside selected output directory; possible overwrite of matching local image.

Preconditions:
- Operator selects/configures the supplied copy JSON and runs a build.
- Target outside output_root is writable and a source image renders successfully.

Limitations:
- No arbitrary source-code execution or write outside host filesystem permissions is claimed.

#### Severity

**Medium** — A less-trusted localization file can steer generated PNG writes and overwrite same-name images in a writable sibling/parent folder, but exploitation requires an operator to build with that file.

Higher if localization JSON is routinely accepted from external contributors in a privileged CI build.

#### Remediation

Validate locale keys as locale identifiers, reject separators and dot/absolute forms, and verify each resolved output path remains under the resolved output_root before creating directories or invoking media tools.

Tests:
- Reject `..`, `../sibling`, absolute and separator-bearing locale keys before any output is created.
- Confirm valid locale keys render under the selected root in direct and guided modes.

<a id="finding-3"></a>

### [3] Unescaped screenshot names and locales can run script in the review sheet

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The source preserves filename stems and locale strings, then interpolates them into HTML without escaping or a CSP. |
| Category | HTML injection in generated review artifact |
| CWE | CWE-79 |
| Affected lines | asc_screens.py:144, asc_screens.py:749, asc_screens.py:759, asc_screens.py:777 |

#### Summary

The generated local asc_review.html embeds locale names and source-derived output filenames directly in HTML text and image attributes. A crafted name can become active markup when an operator opens the review sheet.

#### Root Cause

The contact-sheet builder concatenates untrusted labels and relative paths into raw HTML instead of using context-appropriate escaping.

**Source stem preserved in output filename** — `asc_screens.py:143-144`

An attacker-controlled source filename can survive as the generated PNG filename.

```python
def output_path_for_source(output_dir, source):
    return Path(output_dir) / f"{Path(source).stem}.png"
```

**Locale key preserved** — `asc_screens.py:577-584`

Locale keys from the copy JSON are not escaped or restricted before later display.

```python
def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
```

**Raw HTML interpolation** — `asc_screens.py:755-764`

Both text and quoted attributes receive unescaped content.

```python
        cards.append(
            "\n".join(
                [
                    '<article class="card">',
                    f"<h2>{locale} / {family}</h2>",
                    f'<img src="{relative.as_posix()}" alt="{filename}">',
                    f"<p>{filename}</p>",
                    "</article>",
                ]
            )
```

#### Validation

Filename and locale strings reach element and quoted-attribute contexts without HTML escaping; opening the generated page can interpret crafted markup as script.

Validation method: Static HTML output trace

**Source stem preserved in output filename** — `asc_screens.py:143-144`

An attacker-controlled source filename can survive as the generated PNG filename.

```python
def output_path_for_source(output_dir, source):
    return Path(output_dir) / f"{Path(source).stem}.png"
```

**Locale key preserved** — `asc_screens.py:577-584`

Locale keys from the copy JSON are not escaped or restricted before later display.

```python
def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
```

**Raw HTML interpolation** — `asc_screens.py:755-764`

Both text and quoted attributes receive unescaped content.

```python
        cards.append(
            "\n".join(
                [
                    '<article class="card">',
                    f"<h2>{locale} / {family}</h2>",
                    f'<img src="{relative.as_posix()}" alt="{filename}">',
                    f"<p>{filename}</p>",
                    "</article>",
                ]
            )
```

**Contact sheet written** — `asc_screens.py:776-777`

The active markup is saved as an HTML file the documentation asks the operator to inspect.

```python
    contact_sheet = root / "asc_review.html"
    contact_sheet.write_text(html, encoding="utf-8")
```

Counterevidence and remaining uncertainty:
- The file is a local review artifact and must be opened or published separately.
- Browser file-origin restrictions limit access to unrelated local files.
- The renderer itself does not open a browser.

Limitations:
- No browser payload was executed; host/browser-specific file-origin effects were not tested.

#### Dataflow

source/copy name -\> output path -\> contact-sheet f-string -\> browser parse

- **Source:** Filename stem or locale key

- **Sink:** Raw HTML element/attribute interpolation

- **Outcome:** Active markup in asc_review.html

**Source stem preserved in output filename** — `asc_screens.py:143-144`

An attacker-controlled source filename can survive as the generated PNG filename.

```python
def output_path_for_source(output_dir, source):
    return Path(output_dir) / f"{Path(source).stem}.png"
```

**Locale key preserved** — `asc_screens.py:577-584`

Locale keys from the copy JSON are not escaped or restricted before later display.

```python
def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
```

**Raw HTML interpolation** — `asc_screens.py:755-764`

Both text and quoted attributes receive unescaped content.

```python
        cards.append(
            "\n".join(
                [
                    '<article class="card">',
                    f"<h2>{locale} / {family}</h2>",
                    f'<img src="{relative.as_posix()}" alt="{filename}">',
                    f"<p>{filename}</p>",
                    "</article>",
                ]
            )
```

**Contact sheet written** — `asc_screens.py:776-777`

The active markup is saved as an HTML file the documentation asks the operator to inspect.

```python
    contact_sheet = root / "asc_review.html"
    contact_sheet.write_text(html, encoding="utf-8")
```

#### Reachability

Local content names cross into HTML without escaping.

- **Attacker:** Contributor of screenshot filenames or locale copy JSON

- **Entry point:** Source filename stem or locale key

- **Outcome:** Script execution or review-page manipulation in the contact-sheet context.

Preconditions:
- Operator builds a set that includes the supplied content.
- Operator opens or publishes asc_review.html.

Limitations:
- No claim of automatic host-file read or privilege escalation.

#### Severity

**Low** — Active HTML is reachable from lower-trust filenames/copy metadata, but the contact sheet is local, not automatically opened, and browser file-origin restrictions constrain access to other local files.

Higher if generated review sheets are published on a shared web origin or opened in a privileged embedded browser.

#### Remediation

Escape locale/family/filename in HTML text and attributes, safely encode image URLs, and add a restrictive CSP to the generated contact sheet.

Tests:
- A locale or filename containing quotes and HTML metacharacters renders visibly as text without creating elements or event handlers.
- Relative image references still load for valid Unicode filenames.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Renderer and review artifacts | Untrusted images, locale copy, filenames and local HTML | Reported | Validated locale path escape and local contact-sheet HTML injection; reviewed media command construction, preview, validation, tests and guided wrapper. |
| CI upload handoff | Authenticated ASC --replace and cache marker | Reported | Validated stale-image directory upload; reviewed fingerprint/cache, app/version/localization lookup, argument-array subprocess calls, tests, and documented external CLI assumptions. |
| Package metadata and dependency workflow | Installed entry points and CI dependency audit | No issue found | Reviewed pyproject scripts, dependency-free runtime declaration, dependency-audit workflow, and security policy. Workflow is nonblocking but does not itself perform upload or expose credentials. |
| Media-tool executable boundary | ImageMagick, Apple Frames, FFmpeg subprocesses | No issue found | Reviewed argument-list command construction and tool selection; external decoder vulnerabilities and installed binary provenance are outside this source scan. |

## Open Questions And Follow Up

- The external asc CLI's exact directory filtering, remote App Store acceptance, and configured credentials were not live-verified.
- No media tool execution or browser rendering was performed; findings rely on static source-to-sink evidence.
