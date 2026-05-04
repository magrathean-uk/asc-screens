#!/usr/bin/env python3
import argparse
import colorsys
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


TARGETS = {
    "iphone": (1284, 2778),
    "ipad": (2064, 2752),
}

FRAME_FIT = {
    "iphone": (1080, 2450),
    "ipad": (1840, 2400),
}

DEFAULT_BACKGROUND = ["#060914", "#1A26FF", "#20D7E8"]


@dataclass(frozen=True)
class ImageJob:
    source: Path
    device: str


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
    return sorted(p for p in path.glob("*.png") if p.is_file())


def run(cmd):
    subprocess.run(cmd, check=True)


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


def collect_jobs(input_root):
    root = Path(input_root)
    explicit = []
    for device in ("iphone", "ipad"):
        device_dir = root / device
        if device_dir.is_dir():
            explicit.extend(ImageJob(source=path, device=device) for path in list_pngs(device_dir))

    if explicit:
        return explicit

    mixed = []
    for path in list_pngs(root):
        mixed.append(ImageJob(source=path, device=device_for_path(path)))
    return mixed


def frame_inputs(device, jobs, framed_dir, frames_bin, frame_color):
    files = [job.source for job in jobs if job.device == device]
    if not files:
        return []

    framed_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(frames_bin), "frame", "-o", str(framed_dir)]
    if frame_color:
        cmd += ["-c", frame_color]
    cmd += [str(p) for p in files]
    run(cmd)

    framed = []
    for source in files:
        framed_path = framed_dir / f"{source.stem}_framed.png"
        if not framed_path.exists():
            raise FileNotFoundError(f"Frame output missing: {framed_path}")
        framed.append((source, framed_path))
    return framed


def composite(kind, source, framed, output_dir, background_colors):
    target_w, target_h = target_for_kind(kind)
    max_w, max_h = FRAME_FIT[kind]
    framed_w, framed_h = image_size(framed)
    fit_w, fit_h = fit_inside((framed_w, framed_h), (max_w, max_h))

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / source.name
    run(
        [
            "magick",
            *background_command(target_w, target_h, background_colors),
            "(",
            str(framed),
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


def validate(output_dir):
    if not shutil.which("npx"):
        return
    run(["npx", "appshots", "validate", str(output_dir)])


def process_kind(args, jobs, kind, background_colors):
    output_dir = Path(args.output_root) / kind
    framed_dir = Path(args.output_root) / "_framed" / kind
    framed = frame_inputs(kind, jobs, framed_dir, Path(args.frames_bin), args.frame_color)
    outputs = [composite(kind, source, frame, output_dir, background_colors) for source, frame in framed]
    if args.validate and outputs:
        validate(output_dir)
    return outputs


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
    parser.add_argument("--output-root", default="asc_out", help="Output folder.")
    parser.add_argument("--frames-bin", default=str(Path.home() / ".local/bin/frames"))
    parser.add_argument("--background", help="1 hex color or 3 hex colors, comma or space separated.")
    parser.add_argument("--theme", choices=["teslatlas", "purple"], default="teslatlas")
    parser.add_argument("--frame-color", default="Silver")
    parser.add_argument("--kind", choices=["iphone", "ipad", "all"], default="all")
    parser.add_argument("--validate", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    if not shutil.which("magick"):
        raise SystemExit("Need ImageMagick: brew install imagemagick")

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
        print("No PNGs found")
        return

    background_colors = resolve_background_palette(args.background, args.theme)
    background_colors = prompt_for_background(background_colors)

    kinds = ["iphone", "ipad"] if args.kind == "all" else [args.kind]
    total = 0
    for kind in kinds:
        total += len(process_kind(args, jobs, kind, background_colors))
    print(f"Done: {total} screenshots")


if __name__ == "__main__":
    main()
