# Upload screenshots when design inputs change

`asc-screens-ci` builds screenshots with `asc-screens`, then delegates upload to
an external `asc` executable. Uploads use `--replace` for each locale and device
family. Run it only when replacing those screenshot sets is intended.

The wrapper does not inspect Git history or restrict itself to `main`. Your CI
workflow controls the branch, credentials and when the command runs.

## Before uploading

Install this package from its checkout as described in the [README](../README.md).
The runner also needs ImageMagick, Apple Frames CLI and an authenticated `asc`
executable that accepts the commands below. The target app version and its
localizations must already exist. The wrapper does not create them.

First build locally with `asc-screens --config asc-screens.json` and inspect the
images, output count and `asc_review.html`. Use a fresh output directory when
changing input sets: the renderer does not remove stale images, and the uploader
passes whole directories to `asc`, rather than individual manifest entries.

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
entry to the fingerprint; they do not stop the run. Include all inputs that should
trigger a fresh upload, including this CI configuration when its settings matter.

If `design_inputs` is absent or empty, the wrapper uses the renderer configuration
plus its `source` and `copy_file` values when present. It does not automatically
include tool versions, app source code or the CI configuration. Paths read from
the renderer configuration are still interpreted relative to the CI configuration
for fingerprinting. For nested configurations, list explicit paths relative to
the CI configuration instead.

The default locale is `en-US`; it applies to non-localized output recorded as
`default` in `asc_upload.json`. Other locale keys are used directly. The two device
mappings shown above are the defaults in this checkout. There is no default Mac
mapping. Before uploading Mac screenshots, configure a `mac` mapping verified
against your installed `asc` and target app. Preview videos are not uploaded by
this wrapper.

## Fingerprints and completion markers

Print the cache key without building or uploading:

```bash
asc-screens-ci --config .asc-screens-ci.json --fingerprint-only
```

The key combines app ID, version and a SHA-256 hash of input paths and contents.
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
The [security policy](../SECURITY.md) describes reporting and data boundaries.

## External command contract

The wrapper invokes this sequence with values resolved from configuration and the
upload manifest:

```text
asc auth status --validate
asc versions list --app APP_ID --output json
asc localizations list --version VERSION_ID --output json --locale LOCALE
asc screenshots upload --version-localization LOCALIZATION_ID --path SCREENSHOT_DIR --device-type DEVICE_TYPE --replace
```

Version and localization lookup expects JSON with a `data` array containing `id`
and `attributes`. Versions are matched by `versionString` or `version`;
localizations are matched by `locale`. `--asc-bin` selects a different executable.
These are the commands constructed by this repository, not a guarantee of
compatibility with every external `asc` release.
