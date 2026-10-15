"""Local Apple Frames handoff for composed iPhone and iPad creative assets."""

import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import mkdtemp


# Frames detects several phones by width alone. Keep only complete known panels
# intact; an excerpt with a coincidentally matching width must not be cropped by
# a physical frame. Other captures are contained in the canonical family panel.
_PANELS = {
    "iphone": {(1320, 2868), (1206, 2622), (1260, 2736), (1290, 2796),
               (1179, 2556), (1284, 2778), (1170, 2532), (1242, 2688),
               (1125, 2436), (1080, 2340), (750, 1334), (640, 1136)},
    "ipad": {(2064, 2752), (2048, 2732), (1668, 2420), (1488, 2266),
             (1668, 2388), (1640, 2360), (1620, 2160), (1536, 2048)},
}
_CANONICAL = {"iphone": (1320, 2868), "ipad": (2064, 2752)}


def _run(command):
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _call(command, runner):
    try:
        return runner(command)
    except FileNotFoundError as exc:
        name = "Apple Frames CLI" if Path(str(command[0])).name != "magick" else "ImageMagick"
        raise RuntimeError(f"Need {name} installed locally; no substitute device frame was generated") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Apple Frames rendering failed: {detail}") from exc


def _json(command, runner):
    result = _call(command, runner)
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Apple Frames returned invalid JSON; check its local assets and configuration") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Apple Frames returned an unexpected result")
    return data


def _size(path, runner):
    result = _call(["magick", f"{path}[0]", "-auto-orient", "-format", "%w %h", "info:"], runner)
    try:
        dimensions = tuple(map(int, result.stdout.strip().split()))
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(f"Cannot read device capture dimensions: {path}") from exc
    if len(dimensions) != 2 or min(dimensions) <= 0:
        raise RuntimeError(f"Cannot read device capture dimensions: {path}")
    return dimensions


def _pair(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9]\d*x[1-9]\d*", value):
        raise RuntimeError(f"Apple Frames returned invalid {label}")
    return tuple(map(int, value.split("x")))


def _family(device, kind):
    return isinstance(device, str) and device.casefold().startswith("iphone " if kind == "iphone" else "ipad ")


def _probe(command, path, runner):
    info = _json([*command, "info", str(path)], runner)
    error = info.get("error")
    if error and not (isinstance(error, str) and error.startswith("Unknown device")):
        raise RuntimeError(f"Apple Frames cannot inspect the capture: {error}")
    return info


def _colors(command, info, device, runner):
    if device == info["device"]:
        result = info.get("colors", [])
        if not isinstance(result, list) or any(not isinstance(color, str) for color in result):
            raise RuntimeError("Apple Frames returned invalid frame colors")
        return result
    # list-colors is text even with --json in Frames 1.4.1. The numbered color
    # list is needed only for an explicitly selected compatible model variant.
    result = _call([*command, "--no-color", "list-colors", device], runner)
    return [match.group(1) for line in result.stdout.splitlines()
            if (match := re.fullmatch(r"\s*\d+\. (.+?)(?: \(default\))?\s*", line))]


def render_device_frame(source, output_dir, kind, design=None, runner=None):
    """Return a real, whole Apple Frames PNG plus review metadata.

    Native screenshot panels retain their native model match. Scaled captures
    are resized proportionally and letterboxed, never stretched or cover-cropped.
    This function never installs tools, downloads assets or changes configuration.
    """
    if kind not in _PANELS:
        raise ValueError("Apple Frames composition supports iphone and ipad")
    design, runner = dict(design or {}), runner or _run
    source, output_dir = Path(source).expanduser().resolve(), Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Device capture does not exist: {source}")
    original_size = _size(source, runner)
    frames_bin = design.get("frames_bin") or os.environ.get("ASC_SCREENS_FRAMES_BIN") or "frames"
    command = [str(frames_bin), "--json"]
    if design.get("frame_assets"):
        command += ["--assets", str(Path(design["frame_assets"]).expanduser().resolve())]
    original_info = _probe(command, source, runner)
    device = original_info.get("device")
    if device and not _family(device, kind):
        raise ValueError(f"The capture matches {device}, not an {kind} panel")
    landscape = original_size[0] > original_size[1]
    portrait_size = original_size[::-1] if landscape else original_size
    native = bool(device) and portrait_size in _PANELS[kind]
    panel_size = original_size if native else _CANONICAL[kind][::-1] if landscape else _CANONICAL[kind]
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(mkdtemp(prefix="apple-frames-", dir=output_dir))
    prepared = work / "capture.png"
    # A PNG copy also makes source orientation agree with the frame matcher.
    _call(["magick", f"{source}[0]", "-auto-orient", "-colorspace", "sRGB",
           "-resize", f"{panel_size[0]}x{panel_size[1]}", "-gravity", "center",
           "-background", "black", "-extent", f"{panel_size[0]}x{panel_size[1]}", str(prepared)], runner)
    info = _probe(command, prepared, runner)
    if not _family(info.get("device"), kind):
        raise RuntimeError("Apple Frames has no matching local device assets for the prepared capture")
    requested_device = design.get("frame_device")
    compatible = {info["device"], *(info.get("variants") or [])}
    if requested_device and requested_device not in compatible:
        raise ValueError(f"Frame {requested_device!r} is incompatible with the {panel_size[0]}x{panel_size[1]} capture")
    selected_device = requested_device or info["device"]
    colors = _colors(command, info, selected_device, runner)
    preferred = design.get("frame_color")
    if preferred:
        selected_color = next((color for color in colors if color.casefold() == str(preferred).casefold()), None)
        if selected_color is None:
            raise ValueError(f"Frame color {preferred!r} is unavailable for {selected_device}")
    else:
        selected_color = "Silver" if "Silver" in colors else colors[0] if colors else None
    frame_command = [*command, "frame", "--output", str(work)]
    if selected_color:
        # --colors enables strict color validation instead of a config fallback.
        frame_command += ["--colors", selected_color]
    if requested_device:
        frame_command += ["--device", requested_device]
    receipt = _json([*frame_command, str(prepared)], runner)
    if receipt.get("device") != selected_device or not _family(receipt.get("device"), kind):
        raise RuntimeError("Apple Frames returned a different device than the selected panel")
    if receipt.get("color") != selected_color:
        raise RuntimeError("Apple Frames returned a different frame color")
    if receipt.get("mask_missing") or (kind == "iphone" and not receipt.get("masked")):
        raise RuntimeError("Apple Frames is missing the device mask; restore the local frame assets")
    if _pair(receipt.get("dimensions"), "capture dimensions") != panel_size:
        raise RuntimeError("Apple Frames returned mismatched capture dimensions")
    if not isinstance(receipt.get("output"), str):
        raise RuntimeError("Apple Frames returned no output image")
    output = Path(receipt["output"]).expanduser().resolve()
    if not output.is_relative_to(work) or not output.is_file() or output == prepared or output == source:
        raise RuntimeError("Apple Frames returned an output outside its owned rendering directory")
    framed_size = _size(output, runner)
    if _pair(receipt.get("frame_size"), "frame dimensions") != framed_size:
        raise RuntimeError("Apple Frames output dimensions disagree with its receipt")
    if any(outer < inner for outer, inner in zip(framed_size, panel_size)):
        raise RuntimeError("Apple Frames output is smaller than its device panel")
    return output, {"provider": "Apple Frames", "device": receipt["device"],
                    "color": receipt.get("color"), "original_size": list(original_size),
                    "panel_size": list(panel_size), "framed_size": list(framed_size),
                    "normalized": panel_size != original_size,
                    "screen_offset": [int(info["x"]), int(info["y"])],
                    "masked": bool(receipt.get("masked")), "mask_missing": False,
                    "source_preserved": True}
