# asc-screens Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `asc-screens` from a simple framing CLI to a current-spec, validated, batchable App Store screenshot workflow without breaking the existing `asc-gen` and `asc-screens` entry points.

**Architecture:** Keep the existing local-first Python CLI shape. Extend `asc_screens.py` as the single source of truth for lane specs, detection, validation, and export planning; keep `asc_gen.py` as a guided wrapper. Add only small helper functions and pure-data tables, and prefer manifest/report outputs over editor-style features.

**Tech Stack:** Python 3.10+, setuptools console scripts, ImageMagick CLI, Apple Frames CLI, `unittest`

---

### Task 1: Add current App Store screenshot lane data

**Files:**
- Modify: `asc_screens.py`
- Test: `test_asc_frame_maker.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_target_for_kind_uses_current_highest_required_iphone_size(self):
    self.assertEqual(target_for_kind("iphone"), (1320, 2868))

def test_validate_accepts_current_iphone_and_ipad_lane_sizes(self):
    self.assertEqual(classify_device_from_size(1320, 2868), "iphone")
    self.assertEqual(classify_device_from_size(2064, 2752), "ipad")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_frame_maker.AscFrameMakerTests.test_target_for_kind test_asc_frame_maker.AscFrameMakerTests.test_validate_accepts_current_iphone_and_ipad_lane_sizes`

Expected: FAIL because iPhone target is still `1284x2778` and the new test does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
APP_STORE_IPHONE_TARGETS = (
    (1242, 2688),
    (2688, 1242),
    (1284, 2778),
    (2778, 1284),
    (1290, 2796),
    (2796, 1290),
    (1320, 2868),
    (2868, 1320),
)
```

Keep `TARGETS["iphone"]` computed from the largest portrait lane.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v test_asc_frame_maker.AscFrameMakerTests.test_target_for_kind test_asc_frame_maker.AscFrameMakerTests.test_validate_accepts_current_iphone_and_ipad_lane_sizes`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py test_asc_frame_maker.py README.md
git commit -m "feat: add current app store screenshot lane data"
```

### Task 2: Build first-party validation

**Files:**
- Modify: `asc_screens.py`
- Modify: `asc_gen.py`
- Test: `test_asc_frame_maker.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_validate_png_reports_wrong_size(self):
    report = validate_screenshot_file(Path("bad.png"), size_reader=lambda _: (1080, 1920))
    self.assertFalse(report.ok)
    self.assertIn("size", report.problems[0])

def test_validate_png_rejects_alpha_channel(self):
    report = validate_screenshot_file(
        Path("bad.png"),
        size_reader=lambda _: (1320, 2868),
        alpha_reader=lambda _: True,
    )
    self.assertFalse(report.ok)
    self.assertIn("transparency", report.problems[0].lower())

def test_validate_directory_counts_failures(self):
    summary = validate_output_dir(Path("asc_out/iphone"), files=[Path("ok.png"), Path("bad.png")], validator=fake_validator)
    self.assertEqual(summary.total, 2)
    self.assertEqual(summary.failed, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_frame_maker.AscFrameMakerTests.test_validate_png_reports_wrong_size test_asc_frame_maker.AscFrameMakerTests.test_validate_png_rejects_alpha_channel test_asc_frame_maker.AscFrameMakerTests.test_validate_directory_counts_failures`

Expected: FAIL because validation helpers do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class ValidationReport:
    path: Path
    ok: bool
    problems: tuple[str, ...]
    detected_size: tuple[int, int]

@dataclass(frozen=True)
class ValidationSummary:
    total: int
    passed: int
    failed: int
    reports: tuple[ValidationReport, ...]
```

Implement:
- `supported_sizes_for_kind(kind)`
- `has_alpha(path)`
- `validate_screenshot_file(path, kind=None, ...)`
- `validate_output_dir(output_dir, kind=None, ...)`

Rules:
- accept `.png`, `.jpg`, `.jpeg`
- reject alpha for App Store outputs
- accept any current Apple lane for the family
- print readable summary in CLI
- keep optional `npx appshots` validator out of the default flow

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v test_asc_frame_maker.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py asc_gen.py test_asc_frame_maker.py README.md
git commit -m "feat: add first-party screenshot validation"
```

### Task 3: Expose validation in both CLIs

**Files:**
- Modify: `asc_screens.py`
- Modify: `asc_gen.py`
- Test: `test_asc_gen_cli.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_choose_validation_mode_accepts_check_only(self):
    cli = load_cli()
    self.assertEqual(cli.choose_validation_mode("check"), "check")

def test_count_by_kind_keeps_family_order(self):
    cli = load_cli()
    jobs = [SimpleNamespace(device="ipad"), SimpleNamespace(device="iphone")]
    self.assertEqual(list(cli.count_by_kind(jobs).keys()), ["iphone", "ipad"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_gen_cli.py`

Expected: FAIL because no validation-mode helper exists.

- [ ] **Step 3: Write minimal implementation**

```python
def choose_validation_mode(answer):
    value = answer.strip().lower()
    aliases = {"": "build", "b": "build", "build": "build", "c": "check", "check": "check"}
    if value not in aliases:
        raise ValueError("Choose build or check")
    return aliases[value]
```

Add:
- `asc-screens --check` for validation without framing
- guided prompt in `asc_gen.py` for build vs check
- better empty-input message listing all supported formats, not just PNG

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v test_asc_gen_cli.py test_asc_frame_maker.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py asc_gen.py test_asc_gen_cli.py README.md
git commit -m "feat: expose validation mode in both clis"
```

### Task 4: Add batch family lanes

**Files:**
- Modify: `asc_screens.py`
- Modify: `asc_gen.py`
- Test: `test_asc_frame_maker.py`
- Test: `test_asc_gen_cli.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_expand_kind_selection_for_iphone_latest(self):
    self.assertEqual(expand_export_targets("iphone-latest"), [("iphone", (1320, 2868))])

def test_expand_kind_selection_for_all_latest(self):
    self.assertEqual(
        expand_export_targets("all-latest"),
        [("iphone", (1320, 2868)), ("ipad", (2064, 2752))]
    )

def test_choose_kinds_accepts_latest_aliases(self):
    cli = load_cli()
    self.assertEqual(cli.choose_kinds("latest", []), ["iphone-latest", "ipad-latest"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_frame_maker.py test_asc_gen_cli.py`

Expected: FAIL because export-target expansion does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
EXPORT_FAMILIES = {
    "iphone-latest": [("iphone", (1320, 2868))],
    "ipad-latest": [("ipad", (2064, 2752))],
    "all-latest": [("iphone", (1320, 2868)), ("ipad", (2064, 2752))],
}
```

Refactor `composite()` and `process_kind()` so target size can be passed explicitly while keeping old `iphone` / `ipad` behavior working unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py asc_gen.py test_asc_frame_maker.py test_asc_gen_cli.py README.md
git commit -m "feat: add batch family export lanes"
```

### Task 5: Add CI/config mode

**Files:**
- Modify: `asc_screens.py`
- Create: `asc_screens_config.py`
- Test: `test_asc_frame_maker.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_load_config_reads_json_file(self):
    config = load_config(config_path)
    self.assertEqual(config["source"], "./shots")

def test_main_uses_config_defaults_before_flags(self):
    args = parser.parse_args(["--config", "asc-screens.json"])
    self.assertEqual(resolve_run_settings(args, config)["output_root"], "build/asc")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_frame_maker.py`

Expected: FAIL because config loading does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
```

Support:
- `--config asc-screens.json`
- deterministic non-interactive settings
- optional manifest output path

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py asc_screens_config.py test_asc_frame_maker.py README.md
git commit -m "feat: add config-driven ci mode"
```

### Task 6: Add review outputs

**Files:**
- Modify: `asc_screens.py`
- Test: `test_asc_frame_maker.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_write_contact_sheet_manifest_lists_outputs_in_order(self):
    manifest = write_review_manifest(...)
    self.assertEqual(manifest["items"][0]["slot"], 1)

def test_write_contact_sheet_skips_when_no_outputs(self):
    self.assertIsNone(write_review_manifest(...))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_frame_maker.py`

Expected: FAIL because review helpers do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def write_review_manifest(output_root, outputs):
    ...
```

Start with JSON/HTML manifest only. Defer raster contact-sheet composition until manifest order and completeness are stable.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py test_asc_frame_maker.py README.md
git commit -m "feat: add review manifest outputs"
```

### Task 7: Add minimal promo templates and `asc-cli` handoff

**Files:**
- Modify: `asc_screens.py`
- Modify: `asc_gen.py`
- Test: `test_asc_frame_maker.py`
- Test: `test_asc_gen_cli.py`
- Docs: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_apply_template_adds_safe_caption_block(self):
    plan = render_template_plan("title-bottom", "Big title", "Small subtitle")
    self.assertEqual(plan.text_position, "bottom")

def test_write_upload_manifest_groups_by_locale_and_family(self):
    manifest = write_upload_manifest(...)
    self.assertIn("iphone", manifest["families"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest -v test_asc_frame_maker.py test_asc_gen_cli.py`

Expected: FAIL because template and handoff helpers do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
TEMPLATES = {
    "plain": {...},
    "title-bottom": {...},
    "title-top": {...},
}
```

Rules:
- opt-in only
- no freeform editor
- no AI
- captions beside or above device frame, never on Apple bezel
- export JSON handoff suitable for `asc-cli` or later upload tooling

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add asc_screens.py asc_gen.py test_asc_frame_maker.py test_asc_gen_cli.py README.md
git commit -m "feat: add minimal templates and upload handoff"
```

## Self-Review

- Spec coverage: validation, current lanes, batch families, CI/config, review outputs, minimal templates, localization-adjacent handoff are all mapped to tasks.
- Placeholder scan: no `TODO`/`TBD` markers remain.
- Type consistency: `ValidationReport`, `ValidationSummary`, `expand_export_targets()`, `write_review_manifest()`, and `write_upload_manifest()` are named consistently across tasks.
