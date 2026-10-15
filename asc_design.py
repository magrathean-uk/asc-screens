"""Deterministic, local editorial compositions from real application captures.

The renderer keeps supplied screenshots whole, with typography and a smooth
background gradient sampled from the supplied app icon.
All coordinates returned by ``render_design`` are final-canvas pixels.
"""

from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from asc_device_frames import render_device_frame
from asc_finish import render_finish
from asc_icon_palette import extract_icon_palette


_FONTS = {
    "regular": (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
    "bold": (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
}
_PALETTES = {
    "light": {"background": "#F4F7FC", "ink": "#0F1D34", "muted": "#61728A",
              "stage": "#E6EDF8", "accent": "#2563EB", "line": "#D7E1F0"},
    "dark": {"background": "#080F1B", "ink": "#F4F8FC", "muted": "#AABAD0",
             "stage": "#102238", "accent": "#29B6F6", "line": "#27415C"},
}


def _run(command):
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Need ImageMagick (magick) on PATH for composed assets") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ImageMagick composition failed: {(exc.stderr or str(exc)).strip()}") from exc


def _font(weight):
    for name in _FONTS[weight]:
        if Path(name).is_file():
            return name
    raise RuntimeError("Composed assets need Arial or DejaVu Sans fonts installed")


def _literal(text):
    # ImageMagick interprets percent properties, backslashes and leading @.
    result = str(text).replace("\\", "\\\\").replace("%", "%%")
    return "\\" + result if result.startswith("@") else result


def _text_args(text, width, pointsize, weight="regular", fill="#000000"):
    return ["-background", "none", "-fill", fill, "-font", _font(weight),
            "-pointsize", str(pointsize), "-interline-spacing", str(round(pointsize * .055)),
            "-gravity", "northwest", "-size", f"{int(width)}x", f"caption:{_literal(text)}"]


def _measure(text, width, pointsize, weight="regular", runner=None):
    result = (runner or _run)(["magick", *_text_args(text, width, pointsize, weight),
                               "-format", "%h", "info:"])
    return int(result.stdout.strip())


def _box(x, y, width, height):
    return {"x": round(x), "y": round(y), "width": max(1, round(width)), "height": max(1, round(height))}


def _size(size):
    values = (size.width, size.height) if hasattr(size, "width") else size
    if len(values) != 2:
        raise ValueError("Design size must contain width and height")
    width, height = values
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 320 for value in (width, height)):
        raise ValueError("Design width and height must be integers of at least 320 pixels")
    return width, height


def _normalise(design):
    if not isinstance(design, dict):
        raise ValueError("Design must be an object")
    result = dict(design)
    for field in ("app_name", "title"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ValueError(f"Design requires a nonempty {field}")
    for field in ("subtitle", "detail"):
        if field in result and not isinstance(result[field], str):
            raise ValueError(f"Design {field} must be text")
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
    accent = result.get("accent")
    if accent is not None and (not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent)):
        raise ValueError("Design accent must be a six-digit hex color, e.g. #7254D6")
    icon = result.get("icon")
    if icon is not None and (not isinstance(icon, (str, Path)) or not str(icon).strip()):
        raise ValueError("Design icon must be a nonempty local image path")
    for field in ("frame_assets", "frames_bin", "frame_device", "frame_color"):
        if field in result and (not isinstance(result[field], (str, Path)) or not str(result[field]).strip()):
            raise ValueError(f"Design {field} must be nonempty text")
    return result


def _fit_text(text, width, max_height, preferred, min_size, max_lines, weight, measure):
    """Find the largest readable font that stays inside its allocated region."""
    lo, hi = max(1, round(min_size)), max(1, round(preferred))
    chosen = None
    while lo <= hi:
        pointsize = (lo + hi) // 2
        height = measure(text, round(width), pointsize, weight)
        # Caption line height varies by font. Its one-line sample gives an
        # actual font-specific limit instead of assuming character counts.
        line_height = measure("Ag", round(width), pointsize, weight)
        if height <= max_height and height <= line_height * max_lines + max_lines - 1:
            chosen = (pointsize, height)
            lo = pointsize + 1
        else:
            hi = pointsize - 1
    if chosen is None:
        raise ValueError("Design copy is too long for this canvas; shorten the title or supporting text")
    return chosen


def _contained(source_size, region):
    scale = min(region["width"] / source_size[0], region["height"] / source_size[1])
    width, height = source_size[0] * scale, source_size[1] * scale
    return _box(region["x"] + (region["width"] - width) / 2,
                region["y"] + (region["height"] - height) / 2, width, height)


def plan_design(size, source_size, design, measure=None, *, icon_palette=None):
    """Plan the composition; optional text measurement makes geometry testable.

    Universal assets use a conservative central composition area. This is a
    design guide, not a substitute for Apple's placement-specific preview.
    """
    width, height = _size(size)
    design = _normalise(design)
    if len(source_size) != 2 or any(not isinstance(value, int) or value <= 0 for value in source_size):
        raise ValueError("Source dimensions must be positive integers")
    measure = measure or _measure
    style, layout = design["style"], design["layout"]
    palette = dict(_PALETTES[style])
    if design.get("accent"):
        palette["accent"] = design["accent"]
    if icon_palette is not None:
        palette["accent"] = icon_palette["accent"]
        palette["gradient_colors"] = list(icon_palette["colors"])
        palette["gradient_source"] = "icon"
    universal = (width, height) == (5244, 2950)
    portrait = height > width
    safe = (_box(width * .105, height * .17, width * .79, height * .66) if universal else
            _box(width * .065, height * .075, width * .87, height * .85))
    sx, sy, sw, sh = (safe[key] for key in ("x", "y", "width", "height"))
    kind = design["media_kind"]
    if kind == "auto":
        ratio = source_size[0] / source_size[1]
        kind = "iphone" if ratio < .62 else "ipad" if ratio < .9 else "image"
    text_width = sw if portrait else sw * (.445 if layout == "hero" else .41)
    scale = width / 3840
    identity_size = max(16, round(width * (.033 if portrait else .018)))
    identity_height = max(identity_size * 1.32, width * (.055 if portrait else .026))
    icon_size = round(identity_height)
    identity_gap = round(width * .012)
    icon_enabled = bool(design.get("icon"))
    name_width = text_width - (icon_size + identity_gap if icon_enabled else 0)
    name_font, name_height = _fit_text(design["app_name"], name_width, identity_height,
                                     identity_size, identity_size * .65, 1, "bold", measure)
    preferred_title = width * (.095 if portrait else .058)
    title_max = sh * (.235 if portrait else .56)
    # An explicit line break is an editorial decision: reduce type before
    # wrapping a deliberately balanced two-line title into three lines.
    title_lines = min(3, len(design["title"].splitlines())) if "\n" in design["title"] else 2
    title_font, title_height = _fit_text(design["title"], text_width, title_max,
                                       preferred_title, preferred_title * .57, title_lines, "bold", measure)
    subtitle_font = round(width * (.031 if portrait else .0195))
    subtitle_height = 0
    if design.get("subtitle", ""):
        subtitle_font, subtitle_height = _fit_text(design["subtitle"], text_width * .96,
            sh * (.085 if portrait else .19), subtitle_font, subtitle_font * .65,
            3, "regular", measure)
    detail_font = round(width * (.022 if portrait else .014))
    detail_height = 0
    if design.get("detail", ""):
        detail_font, detail_height = _fit_text(design["detail"], text_width,
            sh * .07, detail_font, detail_font * .7, 2, "regular", measure)
    gap_identity = width * (.042 if portrait else .027)
    gap_subtitle = width * (.021 if portrait else .019)
    gap_detail = width * (.028 if portrait else .027)
    group_height = (identity_height + gap_identity + title_height +
                    (gap_subtitle + subtitle_height if subtitle_height else 0) +
                    (gap_detail + detail_height if detail_height else 0))
    if group_height > sh:
        raise ValueError("Design copy is too long for the safe composition area; shorten the supporting text")
    if portrait and group_height > sh * .47:
        raise ValueError("Design copy leaves too little space for a readable product image; shorten the copy")
    text_y = sy if portrait else sy + (sh - group_height) / 2
    text_boxes = {}
    icon_box = _box(sx, text_y, icon_size, icon_size) if icon_enabled else None
    text_boxes["app_name"] = dict(_box(sx + (icon_size + identity_gap if icon_enabled else 0),
                                     text_y + (identity_height - name_height) / 2,
                                     name_width, name_height), pointsize=name_font, weight="bold",
                                     text=design["app_name"], color=palette["ink"])
    cursor = text_y + identity_height + gap_identity
    text_boxes["title"] = dict(_box(sx, cursor, text_width, title_height),
                              pointsize=title_font, weight="bold", text=design["title"], color=palette["ink"])
    cursor += title_height
    if subtitle_height:
        cursor += gap_subtitle
        text_boxes["subtitle"] = dict(_box(sx, cursor, text_width * .96, subtitle_height),
                                     pointsize=subtitle_font, weight="regular", text=design["subtitle"],
                                     color=palette["muted"])
        cursor += subtitle_height
    if detail_height:
        cursor += gap_detail
        text_boxes["detail"] = dict(_box(sx, cursor, text_width, detail_height),
                                   pointsize=detail_font, weight="regular", text=design["detail"],
                                   color=palette["muted"])
        cursor += detail_height
    if portrait:
        media_top = cursor + width * .07
        media_region = _box(sx + sw * .035, media_top, sw * .93, sy + sh - media_top)
    else:
        media_x = sx + sw * (.515 if layout == "hero" else .48)
        media_region = _box(media_x, sy, sx + sw - media_x, sh)
    # Raw device plans reserve room around the screen. During rendering, actual
    # Apple Frames dimensions replace this estimate before fitting the layout.
    frame = kind in {"iphone", "ipad"}
    inset = (max(3, round(min(media_region["width"], media_region["height"]) *
                         (.018 if kind == "iphone" else .012))) if frame else
             max(2, round(min(media_region["width"], media_region["height"]) * .002)) if kind == "image" else 0)
    inner_region = _box(media_region["x"] + inset, media_region["y"] + inset,
                        media_region["width"] - inset * 2, media_region["height"] - inset * 2)
    media = _contained(source_size, inner_region)
    device = _box(media["x"] - inset, media["y"] - inset,
                  media["width"] + inset * 2, media["height"] + inset * 2)
    stage_inset = width * .014
    stage = _box(media_region["x"] - stage_inset, media_region["y"] - stage_inset,
                 media_region["width"] + stage_inset * 2, media_region["height"] + stage_inset * 2)
    return {"canvas": {"width": width, "height": height}, "safe_area": safe,
            "text_boxes": text_boxes, "icon_box": icon_box, "media_box": media,
            "device_box": device, "stage_box": stage, "source_size": list(source_size),
            "media_kind": kind, "style": style, "layout": layout, "palette": palette,
            "finish": design["finish"], "motif": "none", "accent_rule_box": None,
            "icon_palette": icon_palette,
            "safe_area_note": "Conservative central composition guide; inspect placement previews." if universal else None,
            "source_preserved": True}


def _inspect(path, runner):
    # Match the orientation applied during rendering before computing aspect.
    result = runner(["magick", f"{path}[0]", "-auto-orient", "-format", "%w %h", "info:"])
    values = result.stdout.strip().split()
    if len(values) != 2:
        raise ValueError(f"Cannot read image dimensions: {path}")
    dimensions = tuple(map(int, values))
    if any(value <= 0 for value in dimensions):
        raise ValueError(f"Invalid image dimensions: {path}")
    return dimensions


def _geometry(box):
    return f"+{box['x']}+{box['y']}"


def _rounded(box, radius):
    return (f"roundrectangle {box['x']},{box['y']} "
            f"{box['x'] + box['width'] - 1},{box['y'] + box['height'] - 1} {round(radius)},{round(radius)}")


def render_design(source, output, size, design, runner=None, *, _icon_palette=None):
    """Render an opaque sRGB PNG and return inspectable composition metadata."""
    runner = runner or _run
    design = _normalise(design)
    source, output = Path(source).expanduser().resolve(), Path(output).expanduser().resolve()
    if source == output or (source.exists() and output.exists() and source.samefile(output)):
        raise ValueError("Design output must not overwrite its source image")
    if not source.is_file():
        raise ValueError(f"Design source does not exist: {source}")
    if output.suffix.lower() != ".png":
        raise ValueError("Composed design output must have a .png extension")
    icon = Path(design["icon"]).expanduser().resolve() if design.get("icon") else None
    if icon is not None:
        if not icon.is_file():
            raise ValueError(f"Design icon does not exist: {icon}")
        if icon == output or (output.exists() and icon.samefile(output)):
            raise ValueError("Design output must not overwrite its icon")
        _inspect(icon, runner)
        if _icon_palette is None:
            _icon_palette = extract_icon_palette(icon, runner=runner)
    source_size = _inspect(source, runner)
    kind = design["media_kind"]
    if kind == "auto":
        ratio = source_size[0] / source_size[1]
        kind = "iphone" if ratio < .62 else "ipad" if ratio < .9 else "image"
    if kind in {"iphone", "ipad"}:
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".asc-device-", dir=output.parent) as temp:
            framed, frame_metadata = render_device_frame(source, Path(temp), kind, design)
            # Fit the entire supplied device asset once. Re-clipping it would
            # remove its buttons, camera cutout or the correct screen corners.
            plan = render_design(framed, output, size, dict(design, media_kind="framed"), runner,
                                 _icon_palette=_icon_palette)
        plan["framed_size"] = plan["source_size"]
        plan["source_size"] = list(source_size)
        plan["media_kind"] = kind
        plan["device_frame"] = frame_metadata
        return plan
    measure = lambda text, width, pointsize, weight: _measure(text, width, pointsize, weight, runner)
    plan = plan_design(size, source_size, design, measure=measure, icon_palette=_icon_palette)
    width, height = (plan["canvas"][key] for key in ("width", "height"))
    palette = plan["palette"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".asc-design-", dir=output.parent) as temp:
        temp = Path(temp)
        media, device = plan["media_box"], plan["device_box"]
        media_path = temp / "media.png"
        runner(["magick", f"{source}[0]", "-auto-orient", "-colorspace", "sRGB", "-resize",
                f"{media['width']}x{media['height']}" + ("" if plan["media_kind"] == "framed" else "!"), str(media_path)])
        stage = plan["stage_box"]
        background = temp / "background.png"
        finish_metadata = render_finish(background, (width, height), palette, stage,
            plan["safe_area"], finish=plan["finish"], motif=plan["motif"], runner=runner,
            stage_radius=width * (.045 if plan["layout"] == "spotlight" else .07))
        plan["finish_background"] = {key: value for key, value in finish_metadata.items() if key != "output"}
        command = ["magick", str(background)]
        if plan["finish"] == "studio" and plan["media_kind"] == "framed":
            # Cast the real device's alpha silhouette, including its hardware,
            # rather than painting another outline around the screenshot.
            padding = max(4, round(width * .025))
            shadow = temp / "device-shadow.png"
            runner(["magick", "-size", f"{media['width'] + padding * 2}x{media['height'] + padding * 2}",
                    "xc:none", str(media_path), "-geometry", f"+{padding}+{padding}",
                    "-compose", "over", "-composite", "-channel", "RGB", "-evaluate", "set", "0",
                    "+channel", "-channel", "A", "-evaluate", "multiply", ".20", "+channel",
                    "-blur", f"0x{max(1, round(width * .006))}", str(shadow)])
            command.extend([str(shadow), "-geometry",
                            f"+{media['x'] - padding}+{media['y'] - padding + round(width * .009)}",
                            "-compose", "over", "-composite"])
        image_card = plan["media_kind"] == "image"
        radius = min(device["width"], device["height"]) * .045
        if image_card:
            shadow = temp / "shadow.png"
            local_device = _box(width * .025, width * .025, device["width"], device["height"])
            runner(["magick", "-size", f"{device['width'] + round(width * .05)}x{device['height'] + round(width * .05)}",
                    "xc:none", "-fill", "#000000", "-draw", _rounded(local_device, radius),
                    "-channel", "A", "-evaluate", "multiply", ".25", "+channel", "-blur", f"0x{max(1, round(width * .008))}", str(shadow)])
            command.extend([str(shadow), "-geometry", f"+{device['x'] - round(width * .025)}+{device['y'] - round(width * .025) + round(width * .009)}",
                            "-compose", "over", "-composite", "-fill", palette["line"],
                            "-draw", _rounded(device, radius)])
            # Only feature cards receive this mask. Real device frames retain
            # their original alpha, camera cutout and physical outline.
            mask = temp / "mask.png"
            margin = max(1, (device["width"] - media["width"]) // 2)
            runner(["magick", "-size", f"{media['width']}x{media['height']}", "xc:black", "-fill", "white",
                    "-draw", _rounded(_box(0, 0, media["width"], media["height"]), max(1, radius - margin)), str(mask)])
            runner(["magick", str(media_path), str(mask), "-alpha", "off", "-compose", "CopyOpacity", "-composite", str(media_path)])
        command.extend([str(media_path), "-geometry", _geometry(media), "-compose", "over", "-composite"])
        if icon is not None:
            box = plan["icon_box"]
            icon_path = temp / "icon.png"
            runner(["magick", f"{icon}[0]", "-auto-orient", "-resize", f"{box['width']}x{box['height']}", str(icon_path)])
            if plan["finish"] == "studio":
                mask = temp / "icon-mask.png"
                runner(["magick", "-size", f"{box['width']}x{box['height']}", "xc:black", "-fill", "white",
                        "-draw", _rounded(_box(0, 0, box["width"], box["height"]), box["width"] * .22), str(mask)])
                runner(["magick", str(icon_path), "(", "+clone", "-alpha", "extract", str(mask),
                        "-compose", "multiply", "-composite", ")", "-alpha", "off", "-compose", "CopyOpacity",
                        "-composite", str(icon_path)])
            command.extend([str(icon_path), "-gravity", "northwest", "-geometry", _geometry(box), "-compose", "over", "-composite"])
        for key, box in plan["text_boxes"].items():
            text_path = temp / f"text-{key}.png"
            runner(["magick", *_text_args(box["text"], box["width"], box["pointsize"], box["weight"], box["color"]), str(text_path)])
            command.extend([str(text_path), "-gravity", "northwest", "-geometry", _geometry(box), "-compose", "over", "-composite"])
        command.extend(["-background", palette["background"], "-alpha", "remove", "-alpha", "off", "-strip",
                        "-colorspace", "sRGB", f"PNG24:{output}"])
        runner(command)
    result = runner(["magick", "identify", "-format", "%w %h %[channels]", str(output)])
    fields = result.stdout.strip().split()
    channels = fields[2].split()[0].lower() if len(fields) >= 3 else ""
    if (len(fields) < 3 or tuple(map(int, fields[:2])) != (width, height) or
            channels.endswith("a") or "alpha" in channels):
        output.unlink(missing_ok=True)
        raise RuntimeError("Composed image failed final size or opacity validation")
    plan["output"] = str(output)
    plan["validated"] = True
    return plan
