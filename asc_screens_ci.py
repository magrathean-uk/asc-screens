#!/usr/bin/env python3
import argparse
import glob
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from asc_screens import load_config


DEFAULT_DEVICE_TYPE_MAP = {
    "iphone": "IPHONE_69",
    "ipad": "IPAD_PRO_3GEN_129",
}

_RENDERER_FILES = ("asc_screens.py", "asc_creative.py", "asc_design.py", "asc_device_frames.py", "asc_finish.py", "asc_icon_palette.py")


def renderer_fingerprint():
    """Invalidate completed builds when the shared composition engine changes."""
    root = Path(__file__).resolve().parent
    hasher = hashlib.sha256()
    for name in _RENDERER_FILES:
        hasher.update(name.encode("utf-8") + b"\0")
        hasher.update((root / name).read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


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
    platform: str
    creative_asset_target: dict | None
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
    for key in ("source", "copy_file", "design_file"):
        value = asc_config.get(key)
        if value:
            inputs.append(value)
    return tuple(inputs)


def iter_input_files(root, design_inputs, excluded_roots=(), excluded_directory_names=()):
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
                if any(resolved.is_relative_to(excluded) for excluded in excluded_roots):
                    continue
                if any(part in excluded_directory_names or part.startswith(".creative-stage-") for part in file_path.parts[:-1]):
                    continue
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


def compute_design_fingerprint(root, design_inputs, excluded_roots=(), excluded_directory_names=()):
    root = Path(root).expanduser().resolve()
    hasher = hashlib.sha256()
    for path, missing in sorted(iter_input_files(root, design_inputs, excluded_roots, excluded_directory_names), key=lambda item: item[1] or fingerprint_label(root, item[0])):
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


def load_ci_config(path, cache_dir=None):
    config_path = Path(path).expanduser().resolve()
    root = config_path.parent
    payload = load_config(config_path)
    asc_screens_config_value = payload.get("asc_screens_config", "asc-screens.json")
    asc_screens_config = resolve_root_path(root, asc_screens_config_value)
    asc_config = load_config(asc_screens_config) if asc_screens_config.exists() else {}
    design_inputs = tuple(payload.get("design_inputs") or default_design_inputs(asc_screens_config_value, asc_config))
    # Renderer-owned paths are relative to the renderer config, even when nested.
    if not payload.get("design_inputs"):
        design_inputs = tuple(str(resolve_root_path(asc_screens_config.parent, entry)) for entry in design_inputs[1:])
        design_inputs = (str(asc_screens_config), *design_inputs)
        design_value = asc_config.get("design_file")
        if design_value:
            design_path = resolve_root_path(asc_screens_config.parent, design_value)
            if design_path.is_file():
                design = load_config(design_path)
                if design.get("icon"):
                    # Artwork references belong to the design JSON, which may
                    # live in a different directory from the renderer config.
                    icon_path = resolve_root_path(design_path.parent, os.path.expandvars(design["icon"]))
                    design_inputs = (*design_inputs, str(icon_path))
    if payload.get("output_root"):
        output_root = resolve_root_path(root, payload["output_root"])
    else:
        output_root = resolve_root_path(asc_screens_config.parent, asc_config.get("output_root", "asc_out"))
    device_type_map = {**DEFAULT_DEVICE_TYPE_MAP, **payload.get("device_type_map", {})}
    if payload.get("design_inputs"):
        input_fingerprint = compute_design_fingerprint(root, design_inputs)
    else:
        excluded_roots = (output_root.resolve(), Path(cache_dir or root / ".asc-screens-cache").expanduser().resolve())
        excluded_names = {".git", ".asc-screens-cache", "asc_out", "_framed", "__pycache__"}
        input_fingerprint = compute_design_fingerprint(root, design_inputs, excluded_roots, excluded_names)
    settings = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(("asc-screens-ci-v3\0" + renderer_fingerprint() + "\0" +
                                  settings + "\0" + input_fingerprint).encode()).hexdigest()
    target = payload.get("creative_asset_target")
    if target is not None:
        if not isinstance(target, dict) or target.get("kind") not in {"version", "custom-page", "experiment-treatment"}:
            raise SystemExit("creative_asset_target.kind must be version, custom-page, or experiment-treatment")
        if target["kind"] != "version" and not isinstance(target.get("localization_ids"), dict):
            raise SystemExit("creative_asset_target requires locale-to-ID localization_ids")
        if target["kind"] != "version" and any(not isinstance(locale, str) or not isinstance(value, str) or not value.strip() for locale, value in target["localization_ids"].items()):
            raise SystemExit("creative_asset_target.localization_ids must map locale strings to nonempty ID strings")
    platform = str(payload.get("platform", "IOS"))
    if platform not in {"IOS", "MAC_OS", "TV_OS", "VISION_OS"}:
        raise SystemExit("platform must be IOS, MAC_OS, TV_OS, or VISION_OS")
    return CiConfig(
        root=root,
        app_id=str(payload.get("app_id", "")),
        version=str(payload.get("version", "")),
        asc_screens_config=asc_screens_config,
        output_root=output_root,
        design_inputs=design_inputs,
        device_type_map=device_type_map,
        default_locale=str(payload.get("default_locale", "en-US")),
        platform=platform,
        creative_asset_target=target,
        fingerprint=fingerprint,
    )


def run_command(cmd, runner=subprocess.run, capture_json=False):
    kwargs = {"check": True, "text": True}
    if capture_json:
        kwargs["capture_output"] = True
    try:
        result = runner(cmd, **kwargs)
    except subprocess.CalledProcessError as error:
        # asc preserves reserved media IDs in partial JSON receipts on failure.
        if capture_json:
            if error.stdout:
                print(error.stdout, file=sys.stderr)
            if error.stderr:
                print(error.stderr, file=sys.stderr)
        raise
    if capture_json:
        return json.loads(result.stdout or "{}")
    return result


def find_version_id(payload, version):
    matches = []
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        if attrs.get("versionString") == version or attrs.get("version") == version:
            if item.get("id"):
                matches.append(item["id"])
    if len(matches) > 1:
        raise SystemExit(f"Multiple App Store versions match: {version}; select the intended platform")
    if matches:
        return matches[0]
    raise SystemExit(f"App Store version not found: {version}")


def find_localization_id(payload, locale):
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        if attrs.get("locale") == locale:
            return item.get("id")
    raise SystemExit(f"Version localization not found: {locale}")


PLACEMENT_COMMANDS = {
    "version": ["localizations", "placements", "create"],
    "custom-page": ["product-pages", "custom-pages", "localizations", "placements", "create"],
    "experiment-treatment": ["product-pages", "experiments", "treatments", "localizations", "placements", "create"],
}
CREATIVE_PLACEMENTS = {"PRODUCT_PAGE_HEADER_ASSET", "APP_STORE_SEARCH_RESULTS_ASSET"}


def asc_locale(config, locale):
    return config.default_locale if locale == "default" else locale


def preflight_upload_manifest(config):
    """Validate the entire local handoff before any authenticated or replacing call."""
    manifest_path = config.output_root / "asc_upload.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Upload manifest not found: {manifest_path}; build locally first")
    manifest = load_config(manifest_path)
    if not config.app_id:
        raise SystemExit("app_id is required for uploads")
    locales = manifest.get("locales", {})
    creative = manifest.get("creative_assets", [])
    if not isinstance(locales, dict) or not isinstance(creative, list):
        raise SystemExit("Invalid upload manifest: locales must be an object and creative_assets a list")
    screenshots = []
    for locale, families in sorted(locales.items()):
        if not isinstance(families, dict):
            raise SystemExit(f"Invalid screenshot families for locale {locale}")
        if not locale or Path(locale).name != locale or locale in {".", ".."}:
            raise SystemExit(f"Invalid manifest locale: {locale}")
        for family, entries in sorted(families.items()):
            if family not in {"iphone", "ipad", "mac"}:
                raise SystemExit(f"Unsupported screenshot family: {family}")
            device_type = config.device_type_map.get(family)
            if not isinstance(device_type, str) or not device_type.strip():
                raise SystemExit(f"No supported device_type_map configured for {family}")
            if not isinstance(entries, list) or not 1 <= len(entries) <= 10:
                raise SystemExit(f"Screenshot set {locale}/{family} must contain 1 to 10 files")
            directory = (config.output_root / locale / family if locale != "default" else config.output_root / family).resolve()
            declared = set()
            for entry in entries:
                if not isinstance(entry, dict) or not entry.get("filename"):
                    raise SystemExit(f"Invalid screenshot entry for {locale}/{family}")
                filename = entry["filename"]
                if not isinstance(filename, str) or Path(filename).name != filename:
                    raise SystemExit(f"Invalid screenshot filename: {filename}")
                path = (directory / filename).resolve()
                if path.parent != directory or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    raise SystemExit(f"Missing or unsupported screenshot: {path}")
                if entry.get("path"):
                    recorded = resolve_root_path(config.root, entry["path"]).resolve()
                    if recorded != path:
                        raise SystemExit(f"Manifest screenshot path does not match its set: {recorded}")
                declared.add(path)
            actual = {path.resolve() for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}}
            if len(declared) != len(entries) or actual != declared:
                raise SystemExit(f"Screenshot directory differs from manifest: {directory}; rebuild into a fresh output directory")
            screenshots.append({"locale": asc_locale(config, locale), "family": family, "path": str(directory), "device_type": device_type})
    assets = []
    for entry in creative:
        if not isinstance(entry, dict) or entry.get("media_type") not in {"image", "video"} or not entry.get("path"):
            raise SystemExit("Creative asset requires path and image or video media_type")
        path = resolve_root_path(config.root, entry["path"]).resolve()
        suffixes = {"image": {".png", ".jpg", ".jpeg"}, "video": {".mp4", ".m4v", ".mov"}}
        if not path.is_file() or path.suffix.lower() not in suffixes[entry["media_type"]]:
            raise SystemExit(f"Missing or unsupported creative asset: {path}")
        placements = entry.get("placements", [])
        if not isinstance(placements, list) or any(item not in CREATIVE_PLACEMENTS for item in placements):
            raise SystemExit(f"Unsupported creative placement for {path}")
        locale = asc_locale(config, entry.get("locale", "default"))
        if not isinstance(locale, str) or not locale.strip():
            raise SystemExit(f"Invalid creative asset locale for {path}")
        if "poster_time" in entry:
            poster_time, duration = entry["poster_time"], entry.get("duration")
            if entry["media_type"] != "video" or isinstance(poster_time, bool) or isinstance(duration, bool) or not isinstance(poster_time, (int, float)) or not isinstance(duration, (int, float)) or not math.isfinite(poster_time) or not math.isfinite(duration) or not 0 <= poster_time < duration:
                raise SystemExit(f"Creative video poster_time must be finite and satisfy 0 <= poster_time < duration: {path}")
        target = config.creative_asset_target
        if target and placements and target["kind"] != "version" and not target["localization_ids"].get(locale):
            raise SystemExit(f"creative_asset_target.localization_ids is missing locale {locale}")
        assets.append({**entry, "path": str(path), "locale": locale, "placements": placements})
    needs_version = bool(screenshots) or bool(config.creative_asset_target and config.creative_asset_target["kind"] == "version" and any(asset["placements"] for asset in assets))
    if needs_version and not config.version:
        raise SystemExit("version is required for screenshot uploads or version creative placements")
    if not screenshots and not assets:
        raise SystemExit("Upload manifest contains no screenshots or creative assets")
    return {"screenshots": screenshots, "creative_assets": assets, "needs_version": needs_version}


def screenshot_upload_command(asc_bin, screenshot, localization_id):
    return [asc_bin, "screenshots", "upload", "--version-localization", localization_id, "--path", screenshot["path"], "--device-type", screenshot["device_type"], "--replace", "--confirm"]


def creative_upload_command(asc_bin, asset, library_id):
    media = "images" if asset["media_type"] == "image" else "videos"
    return [asc_bin, "asset-library", media, "upload", "--library-id", library_id, "--file", asset["path"], "--category", "CREATIVE_ASSETS", "--output", "json"]


def creative_placement_command(asc_bin, target, asset, localization_id, media_id, placement):
    media_flag = "--image-id" if asset["media_type"] == "image" else "--video-id"
    return [asc_bin, *PLACEMENT_COMMANDS[target["kind"]], "--localization-id", localization_id, media_flag, media_id, "--placement-type", placement, "--placement-group", "DEFAULT_PROFILE", "--output", "json"]


def poster_frame_command(asc_bin, asset, media_id):
    milliseconds = int(asset["poster_time"] * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    timecode = f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"
    return [asc_bin, "asset-library", "videos", "set-poster-frame", "--id", media_id, "--time-code", timecode, "--output", "json"]


def upload_plan(config, asc_bin="asc"):
    plan = preflight_upload_manifest(config)
    commands = []
    for screenshot in plan["screenshots"]:
        commands.append(screenshot_upload_command(asc_bin, screenshot, f"<version-localization:{screenshot['locale']}>"))
    for index, asset in enumerate(plan["creative_assets"], 1):
        commands.append(creative_upload_command(asc_bin, asset, f"<asset-library:app={config.app_id}>"))
        if "poster_time" in asset:
            commands.append(poster_frame_command(asc_bin, asset, f"<uploaded-asset:{index}>"))
        target = config.creative_asset_target
        if target:
            localization_id = f"<version-localization:{asset['locale']}>" if target["kind"] == "version" else str(target["localization_ids"].get(asset["locale"], ""))
            for placement in asset["placements"]:
                commands.append(creative_placement_command(asc_bin, target, asset, localization_id, f"<uploaded-asset:{index}>", placement))
    return {"app_id": config.app_id, "version": config.version, "platform": config.platform, "creative_asset_target": config.creative_asset_target, "commands": commands, "note": "Local plan only. Placeholder IDs are resolved by read-only app/version/library lookups during upload. Creative assets without an explicit target are uploaded to the Asset Library only. No review submission is performed."}


def upload_screenshots(config, asc_bin="asc", runner=subprocess.run):
    plan = preflight_upload_manifest(config)
    run_command([asc_bin, "auth", "status", "--validate"], runner=runner)
    localization_ids = {}
    if plan["needs_version"]:
        versions = run_command([asc_bin, "versions", "list", "--app", config.app_id, "--platform", config.platform, "--version", config.version, "--paginate", "--output", "json"], runner=runner, capture_json=True)
        version_id = find_version_id(versions, config.version)
        locales = {screenshot["locale"] for screenshot in plan["screenshots"]}
        if config.creative_asset_target and config.creative_asset_target["kind"] == "version":
            locales.update(asset["locale"] for asset in plan["creative_assets"] if asset["placements"])
        for locale in sorted(locales):
            localizations = run_command([asc_bin, "localizations", "list", "--version", version_id, "--output", "json", "--locale", locale, "--paginate"], runner=runner, capture_json=True)
            localization_ids[locale] = find_localization_id(localizations, locale)
    library_id = None
    if plan["creative_assets"]:
        library = run_command([asc_bin, "asset-library", "view", "--app", config.app_id, "--output", "json"], runner=runner, capture_json=True)
        library_id = library.get("data", {}).get("id")
        if not library_id:
            raise SystemExit("Asset Library lookup returned no library ID")
    # Every required local path and remote lookup is resolved before replacement.
    for screenshot in plan["screenshots"]:
        run_command(screenshot_upload_command(asc_bin, screenshot, localization_ids[screenshot["locale"]]), runner=runner)
    for asset in plan["creative_assets"]:
        uploaded = run_command(creative_upload_command(asc_bin, asset, library_id), runner=runner, capture_json=True)
        print(json.dumps({"creative_asset_upload": uploaded}))
        media_id = uploaded.get("imageId" if asset["media_type"] == "image" else "videoId")
        if not media_id or uploaded.get("uploaded") is not True or uploaded.get("ready") is not True:
            raise SystemExit("Creative asset upload returned no ready media receipt; inspect the upload receipt before retrying")
        if "poster_time" in asset:
            run_command(poster_frame_command(asc_bin, asset, media_id), runner=runner)
        target = config.creative_asset_target
        if not target or not asset["placements"]:
            continue
        localization_id = localization_ids[asset["locale"]] if target["kind"] == "version" else str(target["localization_ids"][asset["locale"]])
        for placement in asset["placements"]:
            run_command(creative_placement_command(asc_bin, target, asset, localization_id, media_id, placement), runner=runner)


def run_ci(config, cache_dir=None, force=False, asc_bin="asc", runner=subprocess.run, dry_run=False):
    if dry_run:
        return upload_plan(config, asc_bin=asc_bin)
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
    parser.add_argument("--dry-run", action="store_true", help="Validate the existing local manifest and print an upload plan without building, authenticating, or uploading.")
    args = parser.parse_args()
    config = load_ci_config(args.config, cache_dir=args.cache_dir)
    if args.fingerprint_only:
        print(config.cache_key)
        write_github_output(config)
        return
    result = run_ci(config, cache_dir=args.cache_dir, force=args.force, asc_bin=args.asc_bin, dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps(result, indent=2))
        return
    print(f"{result.status}: {result.cache_key}")


if __name__ == "__main__":
    main()
