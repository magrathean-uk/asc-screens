"""Repeatable local App Store campaigns from curated, original app captures.

A schema-version-1 JSON file holds app designs and ordered feature selections.
Paths are relative to that file. ``load_campaign`` validates without rendering;
``render_campaign`` returns published asset, manifest, gallery and receipt paths.
No discovery, authentication, upload or network operation happens here.
"""

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import quote

from asc_creative import CREATIVE_PROFILES, IMAGE_EXTENSIONS, process_creative_assets


SCHEMA_VERSION = 1
DEFAULT_PROFILES = ("header", "search-results", "universal")
SOURCE_EXTENSIONS = IMAGE_EXTENSIONS | {".webp"}
_ID = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must use lowercase letters, numbers, hyphens or underscores")
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _file(value, base, label):
    path = Path(os.path.expandvars(_text(value, label))).expanduser()
    path = (path if path.is_absolute() else base / path).resolve()
    if not path.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {path}")
    if path.suffix.lower() not in SOURCE_EXTENSIONS:
        raise ValueError(f"{label} must be a supported still image: {path}")
    return path


def _profiles(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty list of creative profiles")
    if any(not isinstance(name, str) or name not in CREATIVE_PROFILES for name in value):
        raise ValueError(f"{label} contains an unsupported creative profile")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate profiles")
    return list(value)


def _design(value, base):
    # Mirror the composition's public recipe fields without invoking ImageMagick
    # or writing a temporary recipe during a read-only inventory.
    result = dict(_object(value, "design"))
    for field in ("app_name", "title"):
        _text(result.get(field), f"design {field}")
    for field in ("subtitle", "detail"):
        if field in result and not isinstance(result[field], str):
            raise ValueError(f"design {field} must be text")
    for field, default, options in (
        ("style", "light", ("light", "dark")),
        ("layout", "hero", ("hero", "spotlight")),
        ("media_kind", "auto", ("auto", "iphone", "ipad", "image", "framed")),
        ("finish", "studio", ("flat", "studio")),
        ("motif", "none", ("none", "grid", "orbits", "paths", "corners")),
    ):
        result.setdefault(field, default)
        if result[field] not in options:
            raise ValueError(f"Unsupported design {field}: {result[field]}")
    if "accent" in result and (not isinstance(result["accent"], str) or
                                not re.fullmatch(r"#[0-9A-Fa-f]{6}", result["accent"])):
        raise ValueError("design accent must be a six-digit hex color")
    if "icon" in result:
        result["icon"] = str(_file(result["icon"], base, "design icon"))
    for field in ("frame_assets", "frames_bin"):
        if field in result:
            value = _text(result[field], f"design {field}")
            value = os.path.expandvars(value)
            path = Path(value).expanduser()
            if field != "frames_bin" or path.is_absolute() or "/" in value:
                path = (path if path.is_absolute() else base / path).resolve()
                if field == "frame_assets" and not path.is_dir():
                    raise ValueError(f"design frame_assets does not exist: {path}")
                result[field] = str(path)
    for field in ("frame_device", "frame_color"):
        if field in result:
            _text(result[field], f"design {field}")
    return result


def load_campaign(config_path, apps=None, asset=None):
    """Validate and resolve a selected campaign, without writing or probing images.

    ``apps`` is an optional iterable of app IDs. ``asset`` overrides every
    selected feature's profile list; ``creative-all`` explicitly requests five.
    Crop coordinates refer to the image after applying its orientation metadata.
    Actual image dimensions and crop bounds are checked before rendering starts.
    """
    path = Path(config_path).expanduser().resolve()
    data = _object(json.loads(path.read_text(encoding="utf-8")), "campaign")
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Campaign requires schema_version {SCHEMA_VERSION}")
    defaults = _object(data.get("defaults", {}), "defaults")
    locale = _text(defaults.get("locale", "en-GB"), "defaults locale")
    profiles = _profiles(defaults.get("profiles", list(DEFAULT_PROFILES)), "defaults profiles")
    override = (list(CREATIVE_PROFILES) if asset == "creative-all" else
                _profiles([asset], "asset override") if asset is not None else None)
    raw_apps = data.get("apps")
    if not isinstance(raw_apps, list) or not raw_apps:
        raise ValueError("apps must be a nonempty list")
    requested = set(apps or ())
    for name in requested:
        _identifier(name, "app filter")
    known = set()
    selected = []
    for raw in raw_apps:
        app = _object(raw, "app")
        app_id = _identifier(app.get("id"), "app id")
        if app_id in known:
            raise ValueError(f"Duplicate app id: {app_id}")
        known.add(app_id)
        if requested and app_id not in requested:
            continue
        name = _text(app.get("name"), "app name")
        base_design = _object(app.get("design"), "app design")
        raw_features = app.get("features")
        if not isinstance(raw_features, list) or not raw_features:
            raise ValueError(f"{app_id}: features must be a nonempty list")
        features, feature_ids = [], set()
        for raw_feature in raw_features:
            feature = _object(raw_feature, "feature")
            feature_id = _identifier(feature.get("id"), "feature id")
            if feature_id in feature_ids:
                raise ValueError(f"{app_id}: duplicate feature id: {feature_id}")
            feature_ids.add(feature_id)
            source = _file(feature.get("source"), path.parent, "feature source")
            crop = feature.get("crop")
            if crop is not None and (not isinstance(crop, list) or len(crop) != 4 or
                                     any(type(v) is not int for v in crop) or
                                     crop[0] < 0 or crop[1] < 0 or crop[2] <= 0 or crop[3] <= 0):
                raise ValueError(f"{app_id}/{feature_id}: crop must be [x,y,width,height] with integer coordinates")
            merged = dict(base_design)
            merged.update(_object(feature.get("design", {}), "feature design"))
            declared = _profiles(feature.get("profiles", profiles), "feature profiles")
            features.append({"id": feature_id, "source": str(source), "crop": crop,
                             "design": _design(merged, path.parent), "profiles": override or declared,
                             "rationale": _text(feature.get("rationale"), "feature rationale")})
        selected.append({"id": app_id, "name": name, "features": features})
    if requested - known:
        raise ValueError("Unknown app filter: " + ", ".join(sorted(requested - known)))
    return {"schema_version": SCHEMA_VERSION, "config": str(path), "locale": locale,
            "apps": selected}


def _digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _renderer_identity():
    root = Path(__file__).resolve().parent
    return {name: _digest(root / name) for name in
            ("asc_campaign.py", "asc_design.py", "asc_creative.py", "asc_device_frames.py", "asc_finish.py", "asc_icon_palette.py")}


def campaign_fingerprint(campaign):
    """Hash configuration, selected inputs and shared rendering implementation."""
    inputs = {campaign["config"]}
    for app in campaign["apps"]:
        for feature in app["features"]:
            inputs.add(feature["source"])
            if feature["design"].get("icon"):
                inputs.add(feature["design"]["icon"])
    selection = json.loads(json.dumps(campaign))
    for app in selection["apps"]:
        for feature in app["features"]:
            feature.pop("source_size", None)
    payload = {"schema_version": SCHEMA_VERSION, "selection": selection,
               "inputs": {name: _digest(name) for name in sorted(inputs)},
               "renderer": _renderer_identity()}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"fingerprint": hashlib.sha256(encoded).hexdigest(), **payload}


def _run(command):
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Need ImageMagick (magick) on PATH for campaign rendering") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Campaign image processing failed: {(exc.stderr or str(exc)).strip()}") from exc


def _oriented_size(source):
    values = _run(["magick", f"{source}[0]", "-auto-orient", "-format", "%w %h", "info:"]).stdout.split()
    if len(values) != 2 or any(not part.isdigit() for part in values):
        raise ValueError(f"Cannot determine image size: {source}")
    return tuple(int(part) for part in values)


def _check_crops(campaign):
    sizes = {}
    for app in campaign["apps"]:
        for feature in app["features"]:
            source = feature["source"]
            if source not in sizes:
                sizes[source] = _oriented_size(source)
            width, height = sizes[source]
            if feature["crop"]:
                x, y, crop_width, crop_height = feature["crop"]
                if x + crop_width > width or y + crop_height > height:
                    raise ValueError(f"{app['id']}/{feature['id']}: crop exceeds oriented source bounds {width}x{height}")
            feature["source_size"] = [width, height]
            icon = feature["design"].get("icon")
            if icon and icon not in sizes:
                sizes[icon] = _oriented_size(icon)


def _protected(campaign):
    paths = {Path(campaign["config"])}
    for app in campaign["apps"]:
        for feature in app["features"]:
            paths.add(Path(feature["source"]))
            if feature["design"].get("icon"):
                paths.add(Path(feature["design"]["icon"]))
    return paths


def _check_output(root, campaign):
    if root.exists() and not root.is_dir():
        raise ValueError(f"Campaign output must be a directory: {root}")
    if any(path.is_relative_to(root) for path in _protected(campaign)):
        raise ValueError("Campaign output must not contain source images, icons or configuration")
    # Reject existing aliases before any rendering. This includes aliases that
    # point back inside the root and would silently merge two feature folders.
    for app in campaign["apps"]:
        for feature in app["features"]:
            for relative in (Path(app["id"]), Path(app["id"]) / feature["id"],
                             *(Path(app["id"]) / feature["id"] / name for name in feature["profiles"])):
                path = root / relative
                if path.is_symlink() or (path.exists() and not path.is_dir()):
                    raise ValueError(f"Campaign output directory is an alias or file: {path}")


def _json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _url(path):
    return html.escape(quote(Path(path).as_posix()), quote=True)


def _gallery(title, entries, base, root, fingerprint):
    cards = []
    for entry in entries:
        relative = Path(entry["path"]).relative_to(root)
        relative = Path(os.path.relpath(root / relative, base))
        url = _url(relative)
        label = html.escape(f"{entry['app_name']} · {entry['feature_id']} · {entry['profile']}")
        title_text = html.escape(entry["campaign_design"]["title"]).replace("\n", "<br>")
        rationale = html.escape(entry["rationale"])
        cards.append(f'<article><a href="{url}"><img src="{url}" alt="{label}" loading="lazy"></a>'
                     f'<h2>{title_text}</h2><p>{label}</p><p>{rationale}</p></article>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>'
            'body{margin:0;padding:clamp(18px,4vw,60px);font:16px/1.55 system-ui,sans-serif;'
            'background:#edf2f9;color:#15233a}header{max-width:960px;margin-bottom:32px}'
            'h1{font-size:clamp(28px,4vw,48px);line-height:1.1}h2{font-size:23px;line-height:1.2}'
            'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:28px}'
            'article{background:white;padding:20px;border-radius:20px;overflow:hidden}'
            'img{display:block;width:100%;height:320px;object-fit:contain;background:#e7edf7;border-radius:10px}'
            'p{color:#526179}code{font-size:12px;overflow-wrap:anywhere}a{color:inherit}'
            '</style><header>' + f'<h1>{html.escape(title)}</h1>'
            '<p>Curated feature messages composed from original app captures. '
            'This review shows the exact exported images.</p>'
            f'<code>schema {SCHEMA_VERSION} · {html.escape(fingerprint)}</code></header>'
            '<main>' + ''.join(cards) + '</main></html>')


def _normalise_source(feature, destination):
    command = ["magick", f"{feature['source']}[0]", "-auto-orient"]
    if feature["crop"]:
        x, y, width, height = feature["crop"]
        command += ["-crop", f"{width}x{height}+{x}+{y}", "+repage"]
    command += ["-colorspace", "sRGB", "-strip", f"PNG:{destination}"]
    _run(command)


def _publication_paths(stage, root, campaign):
    protected = _protected(campaign)
    jobs = []
    for source in sorted(stage.rglob("*")):
        if not source.is_file():
            continue
        target = root / source.relative_to(stage)
        for path in (target, *target.parents):
            if path == root.parent:
                break
            if path.is_symlink():
                raise ValueError(f"Campaign output cannot pass through a symlink: {path}")
        if target.exists() and (not target.is_file() or any(target.samefile(path) for path in protected)):
            raise ValueError(f"Campaign output overlaps an original input: {target}")
        jobs.append((source, target))
    return jobs


def render_campaign(config_path, output_root="asc_out/campaigns", apps=None, asset=None):
    """Render selected app features, then publish manifests and local galleries.

    All selected paths, recipes and crop bounds pass preflight before generation.
    A failed render leaves the previous exports in place. Scratch images use the
    caller's routed TMPDIR; originals are never overwritten. Output is relative
    to the caller's working directory, independently of configuration location.
    """
    campaign = load_campaign(config_path, apps, asset)
    root = Path(output_root).expanduser().resolve()
    _check_output(root, campaign)
    _check_crops(campaign)
    receipt = campaign_fingerprint(campaign)
    all_entries = []
    with TemporaryDirectory(prefix="asc-campaign-") as temporary:
        scratch = Path(temporary)
        stage = scratch / "published"
        stage.mkdir()
        for app in campaign["apps"]:
            entries = []
            for feature in app["features"]:
                normal = scratch / f"{app['id']}-{feature['id']}.png"
                _normalise_source(feature, normal)
                feature_stage = stage / app["id"] / feature["id"]
                for profile in feature["profiles"]:
                    process_creative_assets(normal, feature_stage, profile,
                                            locale=campaign["locale"], design=feature["design"])
                    rendered = json.loads((feature_stage / "asc_upload.json").read_text(encoding="utf-8"))
                    for entry in rendered["creative_assets"]:
                        entry["path"] = str(root / Path(entry["path"]).relative_to(stage))
                        if entry.get("design"):
                            entry["design"]["output"] = entry["path"]
                        entry.update({"source": feature["source"], "app_id": app["id"], "app_name": app["name"],
                                      "feature_id": feature["id"], "rationale": feature["rationale"],
                                      "campaign_design": feature["design"],
                                      "campaign_fingerprint": receipt["fingerprint"],
                                      "source_provenance": {"original": feature["source"],
                                          "sha256": receipt["inputs"][feature["source"]],
                                          "oriented_size": feature["source_size"], "crop": feature["crop"],
                                          "coordinate_space": "after-auto-orient"}})
                        entries.append(entry)
                feature_entries = [entry for entry in entries if entry["feature_id"] == feature["id"]]
                _json(feature_stage / "asc_upload.json", {"locales": {}, "creative_assets": feature_entries})
                _json(feature_stage / "asc_creative_review.json", {"creative_assets": feature_entries})
                (feature_stage / "asc_creative_review.html").write_text(
                    _gallery(app["name"], feature_entries, root / app["id"] / feature["id"], root,
                             receipt["fingerprint"]), encoding="utf-8")
            app_stage = stage / app["id"]
            _json(app_stage / "asc_upload.json", {"locales": {}, "creative_assets": entries})
            _json(app_stage / "campaign_receipt.json", {**receipt, "app_id": app["id"], "creative_assets": entries})
            (app_stage / "index.html").write_text(
                _gallery(app["name"], entries, root / app["id"], root, receipt["fingerprint"]), encoding="utf-8")
            all_entries.extend(entries)
        _json(stage / "campaign_receipt.json", {**receipt, "creative_assets": all_entries})
        (stage / "index.html").write_text(
            _gallery("App Store campaigns", all_entries, root, root, receipt["fingerprint"]), encoding="utf-8")
        # Preflight every final file before publication, including existing aliases.
        jobs = _publication_paths(stage, root, campaign)
        for source, target in jobs:
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(prefix=".campaign-publish-", dir=target.parent, delete=False) as handle:
                pending = Path(handle.name)
            try:
                shutil.copyfile(source, pending)
                pending.replace(target)
            finally:
                pending.unlink(missing_ok=True)
    return [target for _, target in jobs]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Curated campaign JSON")
    parser.add_argument("--app", action="append", help="App ID to render; repeat or omit for all apps")
    parser.add_argument("--asset", choices=[*CREATIVE_PROFILES, "creative-all"], help="Override selected profiles")
    parser.add_argument("--output-root", default="asc_out/campaigns", help="Output directory relative to cwd")
    parser.add_argument("--list", action="store_true", help="Validate and list selected recipes without rendering")
    args = parser.parse_args(argv)
    try:
        if args.list:
            campaign = load_campaign(args.config, args.app, args.asset)
            print(json.dumps(campaign, indent=2))
        else:
            outputs = render_campaign(args.config, args.output_root, args.app, args.asset)
            print(f"Rendered campaign: {Path(args.output_root).expanduser().resolve() / 'index.html'}")
            print(f"Published {len(outputs)} asset and review files")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"asc-campaign: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
