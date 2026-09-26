# Security Policy

## System and scope

`asc-screens` is a local Python command-line tool that processes screenshots, produces optional App Preview videos, and writes output selected by the operator. Its optional `asc-screens-ci` command delegates App Store Connect uploads to a separately installed `asc` CLI.

This repository does not provide a network service, App Store credential store, or App Store authentication implementation. ImageMagick, Apple Frames, FFmpeg, and `asc` are external tools with their own security boundaries.

## Private reporting

Send a report privately to `contact@magrathean.uk` with the subject `SECURITY: asc-screens`. Include the affected version or commit, platform, reproduction steps, impact, and redacted evidence.

Do not include credentials, private keys, signing certificates, database dumps, or unredacted screenshots that contain sensitive data.

## Trust boundaries and reportable findings

The operator chooses local image, video, configuration, copy, and output paths. Rendering passes paths to local external tools. The upload handoff calls the authenticated external `asc` CLI and can replace screenshots for the configured app version.

Report a vulnerability when it can realistically cause an unintended command to run, expose or alter local files outside the chosen operation, disclose credentials or sensitive screenshot data, bypass the intended upload target or authorization context, or affect another user's data or account. A defect that requires a fully trusted local configuration and affects only the operator's intended files normally has lower security impact unless it crosses one of these boundaries.

## Limitations

The package metadata declares no Python runtime dependencies. External tools and their authentication or update paths are outside this repository and should be assessed separately. This policy describes reporting scope; it is not a security audit or a statement that a control has been independently verified.

## Safe harbour

Magrathean UK Ltd. will not pursue a good-faith researcher for security disclosures that:

- Target non-production test systems or researcher-owned environments;
- Avoid persistence, destructive changes, denial of service, and access to personal or customer data;
- Report promptly and permit reasonable time for remediation;
- Do not condition non-disclosure on financial compensation.

No safe harbour covers phishing, credential stuffing, accessing private production infrastructure, large-scale scanning, denial of service, or unlawful conduct.
