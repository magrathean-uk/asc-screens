#!/usr/bin/env python3
import argparse
import colorsys
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


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

APP_STORE_IPAD_TARGETS = (
    (2064, 2752),
    (2752, 2064),
    (2048, 2732),
    (2732, 2048),
    (1668, 2420),
    (2420, 1668),
    (1488, 2266),
    (2266, 1488),
)

TARGETS = {
    "iphone": max((size for size in APP_STORE_IPHONE_TARGETS if size[1] > size[0]), key=lambda size: size[0] * size[1]),
    "ipad": max((size for size in APP_STORE_IPAD_TARGETS if size[1] > size[0]), key=lambda size: size[0] * size[1]),
}

FRAME_FIT = {
    "iphone": (1080, 2450),
    "ipad": (1840, 2400),
}

TEMPLATES = {
    "plain": {"gravity": None, "title_offset": None, "subtitle_offset": None},
    "title-top": {"gravity": "north", "title_offset": "+0+180", "subtitle_offset": "+0+320"},
    "title-bottom": {"gravity": "south", "title_offset": "+0+320", "subtitle_offset": "+0+180"},
}

EXPORT_TARGETS = {
    "iphone": [("iphone", TARGETS["iphone"])],
    "ipad": [("ipad", TARGETS["ipad"])],
    "all": [("iphone", TARGETS["iphone"]), ("ipad", TARGETS["ipad"])],
    "iphone-latest": [("iphone", TARGETS["iphone"])],
    "ipad-latest": [("ipad", TARGETS["ipad"])],
    "all-latest": [("iphone", TARGETS["iphone"]), ("ipad", TARGETS["ipad"])],
}

DEFAULT_BACKGROUND = ["#060914", "#1A26FF", "#20D7E8"]
GENERATED_DIR_NAMES = {"_framed", "asc_out"}
SCREENSHOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}
VALIDATION_EXTENSIONS = {".png", ".jpg", ".jpeg"}
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
)


@dataclass(frozen=True)
class ImageJob:
    source: Path
    device: str


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


def target_for_kind(kind):
    try:
        return TARGETS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown kind: {kind}") from exc


def fit_inside(source, box):
    source_w, source_h = source
    box_w, box_h = box
    scale = min(box_w / source_w, box_h / source_h, 1)
    return (round(source_w * scale), round(source_h * scale))


def output_path_for_source(output_dir, source):
    return Path(output_dir) / f"{Path(source).stem}.png"


def image_size(path):
    result = subprocess.run(
        ["magick", "identify", "-format", "%w %h", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    width, height = result.stdout.split()
    return int(width), int(height)


def list_pngs(path):
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in SCREENSHOT_EXTENSIONS)


def is_generated_path(path):
    return any(part in GENERATED_DIR_NAMES for part in path.parts)


def list_pngs_recursive(path):
    return sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in SCREENSHOT_EXTENSIONS and not is_generated_path(p)
    )


def run(cmd):
    subprocess.run(cmd, check=True)


def supported_sizes_for_kind(kind):
    if kind == "iphone":
        return APP_STORE_IPHONE_TARGETS
    if kind == "ipad":
        return APP_STORE_IPAD_TARGETS
    raise ValueError(f"Unknown kind: {kind}")


def expand_export_targets(selection):
    try:
        return EXPORT_TARGETS[selection]
    except KeyError as exc:
        raise ValueError(f"Unknown export target: {selection}") from exc


def normalize_hex(color):
    color = color.strip()
    if not color:
        raise ValueError("Empty color")
    if not color.startswith("#"):
        color = f"#{color}"
    value = color[1:]
    if re.fullmatch(r"[0-9a-fA-F]{3}", value):
        value = "".join(ch * 2 for ch in value)
    elif not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError(f"Bad hex color: {color}")
    return f"#{value.upper()}"


def parse_background_spec(text):
    parts = [part for part in re.split(r"[,\s]+", text.strip()) if part]
    colors = [normalize_hex(part) for part in parts]
    if not 1 <= len(colors) <= 3:
        raise ValueError("Background needs 1 to 3 hex colors")
    return colors


def derive_background_palette(base):
    base = normalize_hex(base)
    r = int(base[1:3], 16) / 255.0
    g = int(base[3:5], 16) / 255.0
    b = int(base[5:7], 16) / 255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    def to_hex(hue, lightness, saturation):
        red, green, blue = colorsys.hls_to_rgb(hue % 1.0, max(0.0, min(1.0, lightness)), max(0.0, min(1.0, saturation)))
        return "#%02X%02X%02X" % (round(red * 255), round(green * 255), round(blue * 255))

    return [
        to_hex(h - 0.08, l * 0.72, min(1.0, s * 1.10)),
        to_hex(h, max(0.0, min(1.0, l * 1.02)), min(1.0, s * 0.92)),
        to_hex(h + 0.11, min(1.0, l * 1.18 + 0.04), min(1.0, s * 1.05)),
    ]


def blend_hex(left, right, ratio):
    left = normalize_hex(left)
    right = normalize_hex(right)
    ratio = max(0.0, min(1.0, ratio))
    lr = int(left[1:3], 16)
    lg = int(left[3:5], 16)
    lb = int(left[5:7], 16)
    rr = int(right[1:3], 16)
    rg = int(right[3:5], 16)
    rb = int(right[5:7], 16)
    red = round(lr + (rr - lr) * ratio)
    green = round(lg + (rg - lg) * ratio)
    blue = round(lb + (rb - lb) * ratio)
    return f"#{red:02X}{green:02X}{blue:02X}"


def expand_background_palette(colors):
    if len(colors) == 1:
        return derive_background_palette(colors[0])
    if len(colors) == 2:
        return [colors[0], blend_hex(colors[0], colors[1], 0.5), colors[1]]
    return colors


def resolve_background_palette(spec=None, theme=None):
    if spec:
        colors = parse_background_spec(spec)
        return expand_background_palette(colors)
    if theme == "purple":
        return ["#3B005F", "#16002E", "#040018"]
    return DEFAULT_BACKGROUND[:]


def background_command(width, height, colors):
    if len(colors) != 3:
        raise ValueError("Background palette needs 3 colors")
    base, mid, accent = colors
    return [
        "-size",
        f"{width}x{height}",
        f"xc:{base}",
        "-sparse-color",
        "Barycentric",
        f"0,0 {base} {round(width * 0.52)},{round(height * 0.28)} {mid} {width},{round(height * 0.14)} {accent} {round(width * 0.35)},{height} {base}",
        "-blur",
        "0x48",
    ]


def classify_device_from_size(width, height):
    ratio = min(width, height) / max(width, height)
    return "ipad" if ratio >= 0.64 else "iphone"


def device_for_path(path):
    width, height = image_size(path)
    return classify_device_from_size(width, height)


def has_alpha(path):
    result = subprocess.run(
        ["magick", "identify", "-format", "%[channels]", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return "a" in result.stdout.lower()


def validate_screenshot_file(path, kind, size_reader=image_size, alpha_reader=has_alpha):
    width, height = size_reader(path)
    problems = []
    if path.suffix.lower() not in VALIDATION_EXTENSIONS:
        problems.append("format must be PNG, JPG, or JPEG")
    if (width, height) not in supported_sizes_for_kind(kind):
        problems.append(f"size {width}x{height} is not accepted for {kind}")
    if path.suffix.lower() == ".png" and not problems and alpha_reader(path):
        problems.append("transparency is not allowed for App Store screenshots")
    return ValidationReport(path=path, ok=not problems, problems=tuple(problems), detected_size=(width, height))


def validate_output_dir(output_dir, kind=None, files=None, validator=validate_screenshot_file):
    if kind is None:
        kind = Path(output_dir).name
    selected = files if files is not None else [path for path in list_pngs_recursive(Path(output_dir)) if path.suffix.lower() in VALIDATION_EXTENSIONS]
    reports = tuple(validator(path, kind) for path in selected)
    passed = sum(1 for report in reports if report.ok)
    failed = len(reports) - passed
    return ValidationSummary(total=len(reports), passed=passed, failed=failed, reports=reports)


def print_validation_summary(summary):
    for report in summary.reports:
        marker = "OK" if report.ok else "FAIL"
        detail = ", ".join(report.problems) if report.problems else "ready"
        print(f"{marker} {report.path}: {detail}")
    print(f"Validated {summary.total} screenshot(s): {summary.passed} ok, {summary.failed} failed")
    return 0 if summary.failed == 0 else 1


def collect_jobs(input_root):
    root = Path(input_root)
    explicit = []
    for device in ("iphone", "ipad"):
        for device_dir in sorted(p for p in root.rglob(device) if p.is_dir() and not is_generated_path(p)):
            explicit.extend(ImageJob(source=path, device=device) for path in list_pngs_recursive(device_dir))

    if explicit:
        return explicit

    mixed = []
    for path in list_pngs_recursive(root):
        mixed.append(ImageJob(source=path, device=device_for_path(path)))
    return mixed


def frame_inputs(device, jobs, framed_dir, frames_bin, frame_color):
    files = [job.source for job in jobs if job.device == device]
    if not files:
        return []

    framed_dir.mkdir(parents=True, exist_ok=True)
    framed = []
    for source in files:
        cmd = [str(frames_bin), "frame", "-o", str(framed_dir)]
        if frame_color:
            cmd += ["-c", frame_color]
        cmd.append(str(source))
        try:
            run(cmd)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() if getattr(exc, "stderr", None) else "frame command failed"
            print(f"Skip {source}: {detail}", file=sys.stderr)
            continue
        framed_path = framed_dir / f"{source.stem}_framed.png"
        if not framed_path.exists():
            print(f"Skip {source}: frame output missing", file=sys.stderr)
            continue
        framed.append((source, framed_path))
    return framed


def composite(kind, source, framed, output_dir, background_colors, target_size=None, template="plain", copy=None):
    target_w, target_h = target_size or target_for_kind(kind)
    max_w, max_h = FRAME_FIT[kind]
    framed_w, framed_h = image_size(framed)
    fit_w, fit_h = fit_inside((framed_w, framed_h), (max_w, max_h))
    copy = copy or {"title": "", "subtitle": ""}

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
        ]
    )
    return output


def validate(output_dir, kind):
    summary = validate_output_dir(output_dir, kind=kind)
    return print_validation_summary(summary)


def process_kind(args, jobs, kind, background_colors, target_size=None, template="plain", copy=None):
    output_dir = Path(args.output_root) / kind
    framed_dir = Path(args.output_root) / "_framed" / kind
    framed = frame_inputs(kind, jobs, framed_dir, Path(args.frames_bin), args.frame_color)
    outputs = []
    for source, frame in framed:
        try:
            kwargs = {}
            if target_size is not None:
                kwargs["target_size"] = target_size
            if template != "plain":
                kwargs["template"] = template
            if copy:
                kwargs["copy"] = copy
            outputs.append(composite(kind, source, frame, output_dir, background_colors, **kwargs))
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() if getattr(exc, "stderr", None) else "composite command failed"
            print(f"Skip {source}: {detail}", file=sys.stderr)
    if args.validate and outputs:
        validate(output_dir, kind)
    return outputs


def validate_existing_images(source):
    jobs = collect_jobs(source)
    if not jobs:
        print("No screenshots found. Use PNG, JPG, JPEG, HEIC, HEIF, TIF, or TIFF.")
        return 1
    selected = [job.source for job in jobs]
    exit_code = 0
    for kind in ("iphone", "ipad"):
        files = [path for path in selected if classify_device_from_size(*image_size(path)) == kind]
        if not files:
            continue
        summary = validate_output_dir(source, kind=kind, files=files)
        exit_code = max(exit_code, print_validation_summary(summary))
    return exit_code


def load_config(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_localizations(path):
    payload = load_config(path)
    return {
        locale: {
            "title": str(copy.get("title", "")),
            "subtitle": str(copy.get("subtitle", "")),
        }
        for locale, copy in payload.items()
    }


def resolve_configured_args(args, config, defaults):
    resolved = argparse.Namespace(**vars(args))
    for key, value in config.items():
        if not hasattr(resolved, key):
            continue
        if getattr(resolved, key) == defaults.get(key):
            setattr(resolved, key, value)
    return resolved


def resolve_config_paths(args, config_path):
    resolved = argparse.Namespace(**vars(args))
    config_dir = Path(config_path).expanduser().resolve().parent
    for key in ("source", "output_root", "copy_file"):
        value = getattr(resolved, key, None)
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = config_dir / path
        setattr(resolved, key, path)
    return resolved


def resolve_localized_builds(copy_file=None, locale=None):
    if not copy_file:
        return [(None, {"title": "", "subtitle": ""})]
    localizations = load_localizations(copy_file)
    if locale:
        selected = localizations.get(locale)
        if selected is None:
            raise ValueError(f"Locale not found in copy file: {locale}")
        return [(locale, selected)]
    return sorted(localizations.items())


def default_font():
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def overlay_text_command(width, height, template, copy):
    template_spec = TEMPLATES[template]
    title = copy.get("title", "").strip()
    subtitle = copy.get("subtitle", "").strip()
    if template_spec["gravity"] is None or (not title and not subtitle):
        return []
    command = ["-fill", "#FFFFFF", "-gravity", template_spec["gravity"]]
    font = default_font()
    if font:
        command.extend(["-font", font])
    if title:
        command.extend(
            [
                "-pointsize",
                str(round(width * 0.055)),
                "-annotate",
                template_spec["title_offset"],
                title,
            ]
        )
    if subtitle:
        command.extend(
            [
                "-pointsize",
                str(round(width * 0.032)),
                "-annotate",
                template_spec["subtitle_offset"],
                subtitle,
            ]
        )
    return command


def write_review_manifest(output_root, outputs):
    if not outputs:
        return None
    root = Path(output_root)
    family_order = {"iphone": 0, "ipad": 1}
    ordered = sorted((Path(path) for path in outputs), key=lambda path: (family_order.get(path.parent.name, 99), path.name))
    items = []
    current_family = None
    slot = 0
    for path in ordered:
        family = path.parent.name
        if family != current_family:
            current_family = family
            slot = 1
        else:
            slot += 1
        items.append(
            {
                "family": family,
                "slot": slot,
                "filename": path.name,
                "path": str(path),
            }
        )
    manifest_path = root / "asc_review.json"
    manifest_path.write_text(json.dumps({"items": items}, indent=2), encoding="utf-8")
    return manifest_path


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
            {
                "slot": len(family_bucket) + 1,
                "filename": filename,
                "path": str(path),
            }
        )
    manifest_path = root / "asc_upload.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def write_contact_sheet(output_root, outputs):
    if not outputs:
        return None
    root = Path(output_root)
    cards = []
    for path in sorted((Path(path) for path in outputs)):
        relative = path.relative_to(root)
        if len(relative.parts) == 3:
            locale, family, filename = relative.parts
        elif len(relative.parts) == 2:
            family, filename = relative.parts
            locale = "default"
        else:
            raise ValueError(f"Unexpected output path: {path}")
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
        )
    html = "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>asc review</title>",
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#111827;color:#f9fafb;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.card{background:#1f2937;padding:16px;border-radius:8px}img{width:100%;height:auto;background:#000;border-radius:6px}h2{font-size:14px;margin:0 0 12px}p{font-size:12px;color:#d1d5db}</style>",
            "</head><body><main>",
            *cards,
            "</main></body></html>",
        ]
    )
    contact_sheet = root / "asc_review.html"
    contact_sheet.write_text(html, encoding="utf-8")
    return contact_sheet


def prompt_for_background(default_palette):
    if not sys.stdin.isatty():
        return default_palette
    raw = input(
        "Background color(s). Use 1 to 3 hexes, comma separated. "
        f"Enter for default {','.join(default_palette)}: "
    ).strip()
    if not raw:
        return default_palette
    return resolve_background_palette(raw)


def main():
    parser = argparse.ArgumentParser(description="Make framed App Store Connect screenshots.")
    parser.add_argument("source", nargs="?", default=".", help="Folder with iphone/ and ipad/ inside, or mixed PNGs.")
    parser.add_argument("--config", help="JSON config file for repeatable runs.")
    parser.add_argument("--output-root", default="asc_out", help="Output folder.")
    parser.add_argument("--frames-bin", default=str(Path.home() / ".local/bin/frames"))
    parser.add_argument("--background", help="1 hex color or 3 hex colors, comma or space separated.")
    parser.add_argument("--theme", choices=["teslatlas", "purple"], default="teslatlas")
    parser.add_argument("--frame-color", default="Silver")
    parser.add_argument("--kind", choices=sorted(EXPORT_TARGETS), default="all")
    parser.add_argument("--template", choices=sorted(TEMPLATES), default="plain")
    parser.add_argument("--copy-file", help="JSON file with locale -> {title, subtitle}.")
    parser.add_argument("--locale", help="Build one locale from the copy file.")
    parser.add_argument("--check", action="store_true", help="Validate existing screenshots without framing.")
    parser.add_argument("--validate", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    defaults = {
        action.dest: parser.get_default(action.dest)
        for action in parser._actions
        if action.dest != "help"
    }

    if args.config:
        args = resolve_configured_args(args, load_config(args.config), defaults)
        args = resolve_config_paths(args, args.config)

    if not shutil.which("magick"):
        raise SystemExit("Need ImageMagick: brew install imagemagick")

    if args.check:
        raise SystemExit(validate_existing_images(args.source))

    frames_bin = Path(args.frames_bin)
    if not frames_bin.exists():
        found = shutil.which("frames")
        if found:
            frames_bin = Path(found)
        else:
            raise SystemExit("Need Apple Frames CLI at --frames-bin or on PATH")
    args.frames_bin = str(frames_bin)

    jobs = collect_jobs(args.source)
    if not jobs:
        print("No screenshots found. Use PNG, JPG, JPEG, HEIC, HEIF, TIF, or TIFF.")
        return

    background_colors = resolve_background_palette(args.background, args.theme)
    if not args.config:
        background_colors = prompt_for_background(background_colors)

    total = 0
    outputs = []
    localized_builds = resolve_localized_builds(args.copy_file, args.locale)
    for build_locale, copy in localized_builds:
        scoped_root = Path(args.output_root) / build_locale if build_locale else Path(args.output_root)
        scoped_args = argparse.Namespace(**vars(args))
        scoped_args.output_root = scoped_root
        for kind, target_size in expand_export_targets(args.kind):
            built = process_kind(scoped_args, jobs, kind, background_colors, target_size=target_size, template=args.template, copy=copy)
            outputs.extend(built)
            total += len(built)
    write_review_manifest(args.output_root, outputs)
    write_contact_sheet(args.output_root, outputs)
    write_upload_manifest(args.output_root, outputs)
    print(f"Done: {total} screenshots")


if __name__ == "__main__":
    main()
