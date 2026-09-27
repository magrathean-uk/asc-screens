# Support

Start with the [README](../README.md) for local rendering and the
[upload guide](../docs/asc-upload-ci.md) for fingerprinting and upload behavior.

For ordinary support, use the project's published contact address,
[contact@magrathean.uk](mailto:contact@magrathean.uk). Include the command, package
version or commit, Python version, operating system and relevant external tool
versions. Describe what you expected and what happened, with redacted error output.
For image problems, include dimensions, file format, selected device family and a
small synthetic example when possible.

Do not send App Store credentials, private keys or private screenshots. Report
security issues using the subject and route in [SECURITY.md](SECURITY.md).

## Common problems

| Symptom | What to check |
| --- | --- |
| `Need ImageMagick` | Confirm `magick` is available on `PATH`. |
| Apple Frames CLI not found | Provide `--frames-bin` to `asc-screens`, or make `frames` available on `PATH`. Even Mac-only screenshot builds currently check for it. |
| No screenshots found | Use a supported image format and a directory outside paths named `asc_out` or `_framed`, which discovery excludes. |
| Some inputs are ignored | If named `iphone`, `ipad` or `mac` subdirectories exist, discovery uses those directories rather than loose mixed inputs. |
| Unexpected family or size | Mixed-folder detection uses aspect ratio. Prefer separate device folders for rendering and inspect the result. |
| Fewer images than expected | Read skip messages from frame or composite failures. Check for source files with identical stems that can overwrite the same output name. |
| An upload is skipped | Check the completion marker for the current fingerprint. See the upload guide before using `--force`. |
| Version or localization not found | The upload wrapper expects both to exist in App Store Connect. It does not create them. |
