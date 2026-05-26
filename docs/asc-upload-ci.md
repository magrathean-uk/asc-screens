# ASC Upload-on-Design-Change CI

`asc-screens-ci` wraps `asc-screens` and the external `asc` CLI so pushes only
upload screenshots when tracked design inputs changed.

## Config

Create `.asc-screens-ci.json` in the app repo:

```json
{
  "app_id": "123456789",
  "version": "1.2.3",
  "asc_screens_config": "asc-screens.json",
  "output_root": "asc_out",
  "default_locale": "en-US",
  "design_inputs": [
    "asc-screens.json",
    "source/**",
    "copy.json",
    "Resources/DesignTokens/**",
    "App/UI/**",
    "pyproject.toml"
  ],
  "device_type_map": {
    "iphone": "IPHONE_69",
    "ipad": "IPAD_PRO_3GEN_129"
  }
}
```

If `design_inputs` is omitted, the wrapper hashes the `asc-screens` config,
its `source`, and its `copy_file` when present.

## Local Commands

Print the cache key:

```bash
asc-screens-ci --config .asc-screens-ci.json --fingerprint-only
```

Run build and upload unless the local marker exists:

```bash
asc-screens-ci --config .asc-screens-ci.json
```

## GitHub Actions

```yaml
name: App Store screenshots

on:
  push:
    branches: [main]

jobs:
  screenshots:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install tools
        run: |
          brew install imagemagick asc
          python -m pip install -e .

      - name: Auth asc
        env:
          ASC_KEY_ID: ${{ secrets.ASC_KEY_ID }}
          ASC_ISSUER_ID: ${{ secrets.ASC_ISSUER_ID }}
          ASC_PRIVATE_KEY: ${{ secrets.ASC_PRIVATE_KEY }}
        run: |
          printf '%s' "$ASC_PRIVATE_KEY" > AuthKey.p8
          asc auth login --bypass-keychain --name CI --key-id "$ASC_KEY_ID" --issuer-id "$ASC_ISSUER_ID" --private-key AuthKey.p8

      - name: Fingerprint
        id: fp
        run: asc-screens-ci --config .asc-screens-ci.json --fingerprint-only

      - name: Restore screenshot cache
        id: cache
        uses: actions/cache@v4
        with:
          path: .asc-screens-cache
          key: ${{ steps.fp.outputs.cache_key }}

      - name: Build and upload
        if: steps.cache.outputs.cache-hit != 'true'
        run: asc-screens-ci --config .asc-screens-ci.json

      - name: Review artifacts
        if: steps.cache.outputs.cache-hit != 'true'
        uses: actions/upload-artifact@v4
        with:
          name: asc-screens-review
          path: |
            asc_out/asc_review.html
            asc_out/asc_review.json
            asc_out/asc_upload.json
```

The wrapper calls:

```bash
asc auth status --validate
asc versions list --app "$APP_ID" --output json
asc localizations list --version "$VERSION_ID" --output json --locale "$LOCALE"
asc screenshots upload --version-localization "$VERSION_LOCALIZATION_ID" --path "$SCREENSHOT_DIR" --device-type "$DEVICE_TYPE" --replace
```
