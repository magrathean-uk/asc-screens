"""Extract repeatable, alpha-weighted brand colours from a local app icon.

ImageMagick is used only to decode, orient and sample the icon. Weighted
median-cut quantisation keeps at most twelve swatches; each swatch uses an
actual sampled colour rather than inventing a new hue.
"""

from collections import defaultdict
import colorsys
import hashlib
from pathlib import Path
import re
import subprocess


ALGORITHM_VERSION = 1
_PIXEL = re.compile(r"^\d+,\d+:\s+\([^)]*\)\s+#([0-9a-fA-F]{8}|[0-9a-fA-F]{6})\b")


def _run(command):
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Need ImageMagick (magick) on PATH to read app icon colours") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Cannot read app icon: {(exc.stderr or str(exc)).strip()}") from exc


def _hex(rgb):
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def _distance(first, second):
    return sum((a - b) ** 2 for a, b in zip(first, second)) ** .5


def _quantize(histogram, limit=12):
    """Weighted median cut, retaining sampled RGB representatives."""
    groups = [sorted(histogram.items())]

    def spread(group):
        ranges = [max(rgb[channel] for rgb, _ in group) -
                  min(rgb[channel] for rgb, _ in group) for channel in range(3)]
        channel = max(range(3), key=lambda index: (ranges[index], -index))
        return ranges[channel], channel

    while len(groups) < limit:
        candidates = [(spread(group)[0] * sum(weight for _, weight in group) ** .5,
                       -index, index) for index, group in enumerate(groups) if len(group) > 1]
        if not candidates:
            break
        index = max(candidates)[2]
        group = groups.pop(index)
        channel = spread(group)[1]
        group.sort(key=lambda item: (item[0][channel], item[0]))
        midpoint = sum(weight for _, weight in group) / 2
        running, split = 0, 1
        for position, (_, weight) in enumerate(group[:-1], 1):
            running += weight
            split = position
            if running >= midpoint:
                break
        groups.extend((group[:split], group[split:]))

    swatches = []
    for group in groups:
        weight = sum(value for _, value in group)
        centroid = tuple(sum(rgb[channel] * value for rgb, value in group) / weight
                         for channel in range(3))
        # Pick the closest observed colour, favouring area then RGB for ties.
        rgb = min(group, key=lambda item: (_distance(item[0], centroid), -item[1], item[0]))[0]
        swatches.append((rgb, weight))
    return sorted(swatches, key=lambda item: (-item[1], item[0]))


def extract_icon_palette(icon, runner=None):
    """Return a JSON-safe palette based on visible pixels of ``icon``.

    White/black icon backgrounds do not overwhelm a substantial coloured
    logo. Accent flecks below 2.5% of visible area are excluded from palette
    selection, while transparent RGB contributes no area at all. Greyscale
    icons fall back to their own visible neutral values.
    """
    path = Path(icon).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"App icon is not a readable file: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ValueError(f"Cannot read app icon: {path}") from exc
    result = (runner or _run)(["magick", f"{path}[0]", "-auto-orient", "-colorspace", "sRGB",
                               "-alpha", "on", "-thumbnail", "64x64>", "-depth", "8", "txt:-"])
    histogram = defaultdict(float)
    sampled_pixels = 0
    for line in result.stdout.splitlines():
        match = _PIXEL.match(line)
        if not match:
            continue
        value = match.group(1)
        rgb = tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
        alpha = int(value[6:8], 16) / 255 if len(value) == 8 else 1.0
        sampled_pixels += 1
        if alpha:
            histogram[rgb] += alpha
    if not histogram:
        raise ValueError(f"App icon has no visible pixels or is not a supported image: {path}")

    total = sum(histogram.values())
    swatches = _quantize(histogram)
    substantial = [(rgb, weight) for rgb, weight in swatches if weight >= total * .025]
    if not substantial:
        substantial = swatches[:1]

    def chromatic(rgb):
        _, saturation, brightness = colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))
        # Deep charcoal often has a slight blue tint. Treat that as a neutral
        # ground so a small but substantial coloured mark remains the accent.
        return saturation >= .20 and max(rgb) - min(rgb) >= 36 and brightness >= .25

    candidates = [item for item in substantial if chromatic(item[0])]
    selection = candidates or substantial
    primary = selection[0][0]
    colors = [primary]
    # Retain a second brand hue only when it is visibly different. If the icon
    # has one hue, neutral values from that same icon remain useful endpoints.
    for pool in (selection[1:], substantial):
        for rgb, _ in pool:
            if all(_distance(rgb, chosen) >= 38 for chosen in colors):
                colors.append(rgb)
                break
        if len(colors) >= 2:
            break
    if len(colors) == 1:
        colors.append(primary)
    for rgb, _ in selection[1:]:
        if all(_distance(rgb, chosen) >= 52 for chosen in colors):
            colors.append(rgb)
            break

    return {
        "colors": [_hex(rgb) for rgb in colors],
        "accent": _hex(primary),
        "source": "icon",
        "icon": str(path),
        "source_sha256": digest.hexdigest(),
        "algorithm_version": ALGORITHM_VERSION,
        "sampled_pixels": sampled_pixels,
        "visible_pixel_weight": round(total, 4),
        "selection": "chromatic" if candidates else "neutral",
        "swatches": [{"color": _hex(rgb), "weight": round(weight, 4),
                      "fraction": round(weight / total, 6)} for rgb, weight in swatches],
    }
