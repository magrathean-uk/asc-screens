"""Smooth, local background finishes drawn from the app's icon colours.

The canvas is a single continuous colour field. Product placement geometry is
retained as metadata, but never drawn as a panel, outline or decorative shape.
"""

import math
from pathlib import Path
import re
import subprocess


FINISH_VERSION = 2
FINISHES = ("flat", "studio")
# Legacy recipes remain loadable; these values no longer draw any linework.
MOTIFS = ("none", "grid", "orbits", "paths", "corners")


def _run(command):
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Need ImageMagick (magick) on PATH for graphic finishes") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ImageMagick finish failed: {(exc.stderr or str(exc)).strip()}") from exc


def _color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Finish palette colors must use six-digit hex notation")
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _box(value, name):
    if not isinstance(value, dict) or any(key not in value for key in ("x", "y", "width", "height")):
        raise ValueError(f"Finish {name} must contain x, y, width and height")
    for key in ("x", "y", "width", "height"):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError(f"Finish {name} coordinates must be finite numbers")
    result = {key: round(value[key]) for key in ("x", "y", "width", "height")}
    if result["width"] <= 0 or result["height"] <= 0:
        raise ValueError(f"Finish {name} dimensions must be positive")
    return result


def _gradient_colors(palette):
    colors = palette.get("gradient_colors")
    if colors is None:
        return [palette["accent"], palette["accent"]], "accent-fallback"
    if not isinstance(colors, (list, tuple)) or len(colors) not in (2, 3):
        raise ValueError("Finish gradient_colors must contain two or three hex colors")
    for color in colors:
        _color(color)
    source = palette.get("gradient_source", "icon")
    return list(colors), source if isinstance(source, str) else "icon"


def render_finish(output, size, palette, stage_box, safe_area, finish="studio", motif="none",
                  runner=None, stage_radius=None):
    """Write an opaque sRGB PNG and return JSON-safe evidence about the finish.

    ``studio`` blends the supplied icon colours over the complete canvas, with
    a quiet tint by the text and more colour towards the product. ``flat`` is
    a uniform background. Stage and legacy motif arguments never add graphics.
    """
    if finish not in FINISHES:
        raise ValueError(f"Unsupported design finish: {finish}")
    if motif not in MOTIFS:
        raise ValueError(f"Unsupported design motif: {motif}")
    try:
        width, height = size
    except (ValueError, TypeError) as exc:
        raise ValueError("Finish size must contain width and height") from exc
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (width, height)):
        raise ValueError("Finish width and height must be positive integers")
    if not isinstance(palette, dict) or any(key not in palette for key in ("background", "stage", "accent")):
        raise ValueError("Finish palette requires background, stage and accent colors")
    for key in ("background", "stage", "accent", "ink", "muted", "line"):
        if key in palette:
            _color(palette[key])
    colors, source = _gradient_colors(palette)
    stage, safe = _box(stage_box, "stage_box"), _box(safe_area, "safe_area")
    if not (stage["x"] < width and stage["x"] + stage["width"] > 0 and
            stage["y"] < height and stage["y"] + stage["height"] > 0):
        raise ValueError("Finish stage_box must intersect the canvas")
    if stage_radius is not None and (isinstance(stage_radius, bool) or
            not isinstance(stage_radius, (int, float)) or not math.isfinite(stage_radius) or stage_radius < 0):
        raise ValueError("Finish stage_radius must be a finite nonnegative number")
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("Finish output must have a .png extension")
    # Validate all input before creating even the output directory.
    output.parent.mkdir(parents=True, exist_ok=True)
    runner = runner or _run
    background = palette["background"]
    dark = sum(_color(background)) < 384
    strength_min, strength_max = (.035, .34) if dark else (.025, .265)
    scale = min(1, 768 / max(width, height))
    small_width, small_height = max(1, round(width * scale)), max(1, round(height * scale))
    portrait = height > width
    command = ["magick", "-size", f"{width}x{height}", f"xc:{background}"]
    if finish == "studio":
        # Interpolate a tiny colour strip across the orthogonal axis. Cubic
        # filtering produces a continuous wash without an ellipse or panel.
        command.extend(["(", "("])
        for color in colors:
            command.extend(["-size", "1x1", f"xc:{color}"])
        command.extend(["+append" if portrait else "-append", ")", "-filter", "Cubic",
                        "-resize", f"{small_width}x{small_height}!", "(", "-size",
                        f"{small_height}x{small_width}" if not portrait else f"{small_width}x{small_height}",
                        "gradient:black-white"])
        if not portrait:
            # A quarter turn makes black the left edge, white the right edge.
            command.extend(["-rotate", "-90"])
        command.extend(["-function", "Polynomial", "1,0,0", "-evaluate", "Multiply",
                        f"{strength_max - strength_min:.6f}", "-evaluate", "Add", f"{strength_min:.6f}",
                        ")", "-alpha", "off", "-compose", "CopyOpacity", "-composite",
                        "-filter", "Cubic", "-resize", f"{width}x{height}!", ")",
                        "-compose", "over", "-composite"])
    command.extend(["-alpha", "remove", "-alpha", "off", "-colorspace", "sRGB", "-strip", f"PNG24:{output}"])
    runner(command)
    samples = [(min(width - 1, round(width * fraction)), min(height - 1, round(height * fraction)))
               for fraction in (.10, .50, .90)]
    sample_format = "|".join(f"%[hex:p{{{x},{y}}}]" for x, y in samples)
    check = runner(["magick", "identify", "-format",
                    "%w|%h|%[channels]|%[colorspace]|" + sample_format, str(output)])
    fields = check.stdout.strip().split("|")
    channels = fields[2].lower().split()[0] if len(fields) > 2 and fields[2].strip() else ""
    if (len(fields) != 7 or fields[:2] != [str(width), str(height)] or
            channels.endswith("a") or "alpha" in channels or fields[3].lower() != "srgb" or
            any(not re.fullmatch(r"[0-9a-fA-F]{6}", value) for value in fields[4:])):
        output.unlink(missing_ok=True)
        raise RuntimeError("Graphic finish failed final size, opacity or color validation")
    quiet = ({"x": 0, "y": 0, "width": width, "height": max(0, stage["y"])} if portrait else
             {"x": 0, "y": 0, "width": max(0, stage["x"]), "height": height})
    return {"version": FINISH_VERSION, "finish": finish, "motif": "none", "effective_motif": "none",
            "canvas": {"width": width, "height": height}, "stage_box": stage, "stage_drawn": False,
            "stage_radius": None, "safe_area": safe, "quiet_copy_region": quiet,
            "motif_paths": 0, "motif_opacity": 0, "gradient_source": source,
            "gradient_colors": colors, "gradient_algorithm": "whole-canvas-icon-colour-field-v2",
            "gradient_strength": [strength_min, strength_max] if finish == "studio" else [0, 0],
            "gradient_samples": [{"x": x, "y": y, "color": "#" + color.upper()}
                                 for (x, y), color in zip(samples, fields[4:])],
            "atmosphere_working_size": [small_width, small_height] if finish == "studio" else None,
            "output": str(output), "validated": True}
