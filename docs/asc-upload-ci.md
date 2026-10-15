# Upload screenshots and creative assets when design inputs change

`asc-screens-ci` builds with `asc-screens`, then delegates upload to
an external `asc` executable. Screenshot uploads use `--replace --confirm` for each locale and device
family. Run it only when replacing those screenshot sets is intended.
Creative assets upload to the app's Asset Library, with optional explicit
placement assignment. The integration is checked against `asc` 5.14.3.

The wrapper does not inspect Git history or restrict itself to `main`. Your CI
workflow controls the branch, credentials and when the command runs.

## Before uploading

Install this package from its checkout as described in the [README](../README.md).
The runner also needs the rendering tools for the chosen profile and an
authenticated `asc` executable that accepts the commands below. Apple Frames
is used for device screenshots; creative videos need FFmpeg and FFprobe.
Target versions, custom pages, optimization treatments, and their localizations
must already exist. The wrapper does not create them.

First build locally with `asc-screens --config asc-screens.json` and inspect the
images, output count and `asc_review.html`. Use a fresh output directory when
changing input sets: the renderer does not remove stale images, and the uploader
passes whole screenshot directories to `asc`. Preflight rejects unlisted
screenshot images and missing manifest files before an upload can replace a set.
Creative entries are uploaded individually from the manifest.

## Configuration

Keep `.asc-screens-ci.json` beside `asc-screens.json` in the app repository:

```json
{
  "app_id": "123456789",
  "version": "1.2.3",
  "asc_screens_config": "asc-screens.json",
  "output_root": "asc_out",
  "default_locale": "en-US",
  "design_inputs": [
    ".asc-screens-ci.json",
    "asc-screens.json",
    "source/**",
    "copy.json"
  ],
  "device_type_map": {
    "iphone": "IPHONE_69",
    "ipad": "IPAD_PRO_3GEN_129"
  }
}
```

The app ID and version above are examples. Match `output_root` to the renderer's
output directory. Relative CI paths are resolved against the CI configuration
file's directory. The renderer resolves its paths against its own configuration
file, so keeping both files together avoids different interpretations.

`design_inputs` accepts file paths, directories and glob patterns. Listed files
are hashed whether or not Git tracks them. Missing patterns contribute a missing
entry to the fingerprint; they do not stop the run. Include all artwork and copy
inputs that should trigger a fresh upload. CI settings, including upload targets,
always contribute to the fingerprint.

If `design_inputs` is absent or empty, the wrapper uses the renderer configuration
plus its `source` and `copy_file` values when present. Those default input paths
resolve relative to the renderer configuration, including when it is nested.
The `design_file` and its referenced `icon` also contribute when present; icon
paths resolve beside the design JSON.
Explicit `design_inputs` resolve relative to the CI configuration. Shared
renderer code (`asc_screens.py`, `asc_creative.py`, `asc_design.py`, and
`asc_device_frames.py`, and `asc_finish.py`) always
contributes, including with explicit inputs, so template changes invalidate old
completion markers. External tool versions and unrelated app source code are
not automatically included.
Default discovery excludes the output root, completion cache, Git metadata,
and generated framing/staging directories. Explicit `design_inputs` are hashed
as declared; exclude generated outputs when choosing them.

The default locale is `en-US`; it applies to non-localized output recorded as
`default` in `asc_upload.json`. Other locale keys are used directly. The two device
mappings shown above are the defaults in this checkout. There is no default Mac
mapping. Before uploading Mac screenshots, configure a `mac` mapping verified
against your installed `asc` and target app. Legacy `--preview` videos are not
uploaded by this wrapper. Creative videos from `--asset` are uploaded to the
Asset Library.

## Creative Asset Library and placements

Build using a creative renderer configuration, then inspect
`asc_creative_review.html`. A library-only CI configuration can omit `version`:

```json
{
  "app_id": "123456789",
  "asc_screens_config": "creative-assets.json",
  "output_root": "asc_out",
  "default_locale": "en-GB"
}
```

Header and search image/video entries upload as `CREATIVE_ASSETS`. Event card
and detail exports remain library-only in this handoff; it does not create or
assign In-App Events. The universal PNG can be assigned to both header and
search placements. Posters are local review files rather than separate creative
uploads. The handoff uses video entries' `poster_time` to set the uploaded video's
poster frame before assigning a placement. An uploaded asset or assigned placement has not been submitted or
published by this tool.

To assign header/search entries to the configured app version, add both
`"version": "1.2.3"` and:

```json
"creative_asset_target": {"kind": "version"}
```

For an existing custom product page, supply its localization IDs:

```json
"creative_asset_target": {
  "kind": "custom-page",
  "localization_ids": {"en-GB": "CUSTOM_PAGE_LOCALIZATION_ID"}
}
```

For an existing product page optimization treatment:

```json
"creative_asset_target": {
  "kind": "experiment-treatment",
  "localization_ids": {"en-GB": "TREATMENT_LOCALIZATION_ID"}
}
```

These are alternative target settings; choose one. `platform` defaults to `IOS`
for version lookup; set it explicitly for a different supported app platform.
Map the exact locale keys used by the generated manifest, after `default_locale`
fallback. The default flow uploads to the library without assigning placements.
It does not create a custom page, start an optimization experiment, submit assets,
or publish a version.

Inspect the existing manifest and command plan locally:

```bash
asc-screens-ci --config .asc-screens-ci.json --dry-run
```

Dry run does not build, authenticate, or contact App Store Connect. Remote IDs
that would be discovered or created appear as placeholders. A normal run
validates local files and resolves target IDs before replacing screenshots.

## Fingerprints and completion markers

Print the cache key without building or uploading:

```bash
asc-screens-ci --config .asc-screens-ci.json --fingerprint-only
```

The key combines app ID, version and a SHA-256 hash of CI settings, shared renderer
code, and input paths and contents.
If `GITHUB_OUTPUT` is set, fingerprint-only mode also appends `fingerprint` and
`cache_key` outputs to that file.

Build and upload:

```bash
asc-screens-ci --config .asc-screens-ci.json
```

A successful run creates `<cache_key>.done` in `.asc-screens-cache` under the
current working directory. An existing marker skips both build and upload.
Use `--cache-dir` to choose another location; relative CLI paths are relative to
the current working directory. `--force` ignores the marker and repeats build and
replacement upload even when the fingerprint is unchanged.

The marker records command completion. It does not check that remote screenshots
still exist or match local output. A failure before marker creation can leave
some locales already replaced; review remote state before retrying.

## CI integration

The repository's existing `dependency-audit.yml` scans Python dependencies. It
does not generate or upload screenshots. To integrate the wrapper into a separate
app repository's workflow:

1. Choose the branch and event allowed to replace screenshots.
2. Prepare the renderer, external tools and `asc` authentication using your
   existing runner and secret-handling process.
3. Run fingerprint-only mode and restore completion markers using its exact
   `cache_key`.
4. Run `asc-screens-ci` after restoring markers. It performs its own marker check.
5. Save completion markers only after success. Keep the rendered images together
   with the review HTML and JSON files if storing review artifacts.

Keep credentials and private screenshot content out of logs and public artifacts.
The [security policy](../.github/SECURITY.md) describes reporting and data boundaries.

## External command contract

The wrapper invokes this sequence with values resolved from configuration and the
upload manifest:

```text
asc auth status --validate
asc versions list --app APP_ID --platform IOS --output json --paginate
asc localizations list --version VERSION_ID --output json --locale LOCALE --paginate
asc screenshots upload --version-localization LOCALIZATION_ID --path SCREENSHOT_DIR --device-type DEVICE_TYPE --replace --confirm
```

Version and localization lookup expects JSON with a `data` array containing `id`
and `attributes`. Versions are matched by `versionString` or `version`;
localizations are matched by `locale`. `--asc-bin` selects a different executable.
These are the commands constructed by this repository, not a guarantee of
compatibility with every external `asc` release.

Creative upload discovers the library with `asc asset-library view --app APP_ID`,
then uses `asc asset-library images upload` or `videos upload` with `--library-id`,
`--file`, and `--category CREATIVE_ASSETS`. An explicit target adds the supported
`placements create` command under `localizations`,
`product-pages custom-pages localizations`, or
`product-pages experiments treatments localizations`. Placement types are
`PRODUCT_PAGE_HEADER_ASSET` and `APP_STORE_SEARCH_RESULTS_ASSET`.
