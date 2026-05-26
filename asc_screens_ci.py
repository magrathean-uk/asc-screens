#!/usr/bin/env python3
import argparse
import glob
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from asc_screens import load_config


DEFAULT_DEVICE_TYPE_MAP = {
    "iphone": "IPHONE_69",
    "ipad": "IPAD_PRO_3GEN_129",
}


@dataclass(frozen=True)
class CiConfig:
    root: Path
    app_id: str
    version: str
    asc_screens_config: Path
    output_root: Path
    design_inputs: tuple[str, ...]
    device_type_map: dict
    default_locale: str
    fingerprint: str

    @property
    def cache_key(self):
        return f"asc-screens-{self.app_id}-{self.version}-{self.fingerprint}"


@dataclass(frozen=True)
class CiRunResult:
    status: str
    cache_key: str
    fingerprint: str


def resolve_root_path(root, value):
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return root / path


def default_design_inputs(asc_screens_config, asc_config):
    inputs = [asc_screens_config]
    for key in ("source", "copy_file"):
        value = asc_config.get(key)
        if value:
            inputs.append(value)
    return tuple(inputs)


def iter_input_files(root, design_inputs):
    seen = set()
    missing = []
    for entry in design_inputs:
        pattern = str(resolve_root_path(root, entry))
        matches = [Path(match) for match in glob.glob(pattern, recursive=True)]
        if not matches:
            path = Path(pattern)
            if path.exists():
                matches = [path]
        if not matches:
            missing.append(entry)
            continue
        for match in matches:
            files = sorted(match.rglob("*")) if match.is_dir() else [match]
            for file_path in files:
                if not file_path.is_file():
                    continue
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield resolved, None
    for entry in missing:
        yield None, entry


def fingerprint_label(root, path):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def compute_design_fingerprint(root, design_inputs):
    root = Path(root).expanduser().resolve()
    hasher = hashlib.sha256()
    for path, missing in sorted(iter_input_files(root, design_inputs), key=lambda item: item[1] or fingerprint_label(root, item[0])):
        if missing is not None:
            hasher.update(b"missing\0")
            hasher.update(missing.encode("utf-8"))
            hasher.update(b"\0")
            continue
        label = fingerprint_label(root, path)
        hasher.update(b"file\0")
        hasher.update(label.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def load_ci_config(path):
    config_path = Path(path).expanduser().resolve()
    root = config_path.parent
    payload = load_config(config_path)
    asc_screens_config_value = payload.get("asc_screens_config", "asc-screens.json")
    asc_screens_config = resolve_root_path(root, asc_screens_config_value)
    asc_config = load_config(asc_screens_config) if asc_screens_config.exists() else {}
    design_inputs = tuple(payload.get("design_inputs") or default_design_inputs(asc_screens_config_value, asc_config))
    output_root = resolve_root_path(root, payload.get("output_root") or asc_config.get("output_root", "asc_out"))
    device_type_map = {**DEFAULT_DEVICE_TYPE_MAP, **payload.get("device_type_map", {})}
    fingerprint = compute_design_fingerprint(root, design_inputs)
    return CiConfig(
        root=root,
        app_id=str(payload.get("app_id", "")),
        version=str(payload.get("version", "")),
        asc_screens_config=asc_screens_config,
        output_root=output_root,
        design_inputs=design_inputs,
        device_type_map=device_type_map,
        default_locale=str(payload.get("default_locale", "en-US")),
        fingerprint=fingerprint,
    )


def run_command(cmd, runner=subprocess.run, capture_json=False):
    kwargs = {"check": True, "text": True}
    if capture_json:
        kwargs["capture_output"] = True
    result = runner(cmd, **kwargs)
    if capture_json:
        return json.loads(result.stdout or "{}")
    return result


def find_version_id(payload, version):
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        if attrs.get("versionString") == version or attrs.get("version") == version:
            return item.get("id")
    raise SystemExit(f"App Store version not found: {version}")


def find_localization_id(payload, locale):
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        if attrs.get("locale") == locale:
            return item.get("id")
    raise SystemExit(f"Version localization not found: {locale}")


def upload_screenshots(config, asc_bin="asc", runner=subprocess.run):
    manifest_path = config.output_root / "asc_upload.json"
    manifest = load_config(manifest_path)
    run_command([asc_bin, "auth", "status", "--validate"], runner=runner)
    versions = run_command([asc_bin, "versions", "list", "--app", config.app_id, "--output", "json"], runner=runner, capture_json=True)
    version_id = find_version_id(versions, config.version)
    for locale, families in manifest.get("locales", {}).items():
        asc_locale = config.default_locale if locale == "default" else locale
        localizations = run_command(
            [asc_bin, "localizations", "list", "--version", version_id, "--output", "json", "--locale", asc_locale],
            runner=runner,
            capture_json=True,
        )
        localization_id = find_localization_id(localizations, asc_locale)
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


def run_ci(config, cache_dir=None, force=False, asc_bin="asc", runner=subprocess.run):
    cache_dir = Path(cache_dir or config.root / ".asc-screens-cache")
    marker = cache_dir / f"{config.cache_key}.done"
    if marker.exists() and not force:
        return CiRunResult("skipped", config.cache_key, config.fingerprint)
    run_command(["asc-screens", "--config", str(config.asc_screens_config)], runner=runner)
    upload_screenshots(config, asc_bin=asc_bin, runner=runner)
    cache_dir.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return CiRunResult("uploaded", config.cache_key, config.fingerprint)


def write_github_output(config):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"fingerprint={config.fingerprint}\n")
        handle.write(f"cache_key={config.cache_key}\n")


def main():
    parser = argparse.ArgumentParser(description="Build and upload asc-screens only when design inputs changed.")
    parser.add_argument("--config", default=".asc-screens-ci.json")
    parser.add_argument("--cache-dir", default=".asc-screens-cache")
    parser.add_argument("--asc-bin", default="asc")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fingerprint-only", action="store_true")
    args = parser.parse_args()
    config = load_ci_config(args.config)
    if args.fingerprint_only:
        print(config.cache_key)
        write_github_output(config)
        return
    result = run_ci(config, cache_dir=args.cache_dir, force=args.force, asc_bin=args.asc_bin)
    print(f"{result.status}: {result.cache_key}")


if __name__ == "__main__":
    main()
