"""Local creative-asset exports for App Store headers, search and in-app events.

``validate_creative_file(path, profile)`` returns a tuple of human-readable
problems (an empty tuple means success). ``check_creative_assets`` prints those
diagnostics and returns an exit status. Generation raises on any failed input or
export, so a partial run cannot be reported as a successful asset set.
"""

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import quote


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mov", ".m4v", ".mp4"}
GENERATED_DIR_NAMES = {"asc_out", "_framed"}


@dataclass(frozen=True)
class CreativeProfile:
    title: str
    width: int
    height: int
    min_width: int
    min_height: int
    ratio: tuple[int, int] | None
    placements: tuple[str, ...] = ()
    video: bool = True
    min_duration: int = 5
    max_bytes: int | None = None
    png_only: bool = False


CREATIVE_PROFILES = {
    "header": CreativeProfile("Product page header", 3840, 1646, 3840, 1646, None,
                              ("PRODUCT_PAGE_HEADER_ASSET",)),
    "search-results": CreativeProfile("Search results", 3840, 2560, 1920, 1280, (3, 2),
                                      ("APP_STORE_SEARCH_RESULTS_ASSET",)),
    "universal": CreativeProfile("Universal header and search image", 5244, 2950, 5244, 2950, None,
                                 ("PRODUCT_PAGE_HEADER_ASSET", "APP_STORE_SEARCH_RESULTS_ASSET"),
                                 video=False, png_only=True),
    "event-card": CreativeProfile("In-app event card", 3840, 2160, 1920, 1080, (16, 9),
                                  min_duration=15, max_bytes=500_000_000),
    "event-detail": CreativeProfile("In-app event details", 2160, 3840, 1080, 1920, (9, 16),
                                    min_duration=15, max_bytes=500_000_000),
}


def _profile(name):
    try:
        return CREATIVE_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown creative profile: {name}") from exc


def _profiles(name):
    if name == "creative-all":
        return list(CREATIVE_PROFILES)
    _profile(name)
    return [name]


def _media_type(path):
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    raise ValueError(f"Unsupported creative source type: {path}")


def discover_creative_sources(source, output_root=None, exclude_generated=True):
    """Find local media, excluding generated directories and this run's output."""
    source = Path(source).expanduser().resolve()
    output = Path(output_root).expanduser().resolve() if output_root is not None else None
    if not source.exists():
        raise ValueError(f"Creative source does not exist: {source}")
    if output is not None and source.is_relative_to(output):
        raise ValueError("Creative output directory must not contain the source")
    if source.is_file():
        _media_type(source)
        return [source]
    files = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            continue
        if exclude_generated and any(part in GENERATED_DIR_NAMES for part in path.parts):
            continue
        resolved = path.resolve()
        if output is not None and resolved.is_relative_to(output):
            continue
        files.append(path)
    return files


def _run(command):
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Need {command[0]} on PATH for creative assets") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"{command[0]} failed: {detail}") from exc


def inspect_creative_image(path):
    result = _run(["magick", "identify", "-format", "%m %w %h %[channels]", f"{Path(path).resolve()}[0]"])
    image_format, width, height, channels = result.stdout.strip().split(maxsplit=3)
    channel_name = channels.split()[0].lower()
    return {"format": image_format.upper(), "width": int(width), "height": int(height),
            "alpha": channel_name.endswith("a") or "alpha" in channel_name}


def inspect_creative_video(path):
    result = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,duration:format=duration,format_name",
        "-of", "json", str(Path(path).resolve()),
    ])
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No video stream: {path}")
    stream = streams[0]
    raw_duration = stream.get("duration")
    if raw_duration in (None, "N/A"):
        raw_duration = data.get("format", {}).get("duration")
    duration = float(raw_duration)
    rate = stream.get("avg_frame_rate", "0/0")
    if rate in ("0/0", "0", "N/A"):
        rate = stream.get("r_frame_rate", "0/0")
    fps = float(Fraction(rate))
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"Cannot determine positive video duration and frame rate: {path}")
    return {"width": int(stream["width"]), "height": int(stream["height"]),
            "duration": duration, "fps": fps,
            "format": data.get("format", {}).get("format_name", "")}


def _dimension_problems(width, height, profile):
    if profile.ratio is None:
        if (width, height) != (profile.width, profile.height):
            return [f"Expected size {profile.width}x{profile.height}; got {width}x{height}"]
        return []
    problems = []
    if not (profile.min_width <= width <= profile.width and profile.min_height <= height <= profile.height):
        problems.append(f"Size must be {profile.min_width}x{profile.min_height} through "
                        f"{profile.width}x{profile.height}; got {width}x{height}")
    if width * profile.ratio[1] != height * profile.ratio[0]:
        problems.append(f"Aspect ratio must be {profile.ratio[0]}:{profile.ratio[1]}")
    return problems


def validate_creative_file(path, profile):
    """Return validation problems for one exported image or video (empty = valid)."""
    definition = _profile(profile)
    path = Path(path)
    problems = []
    try:
        if not path.is_file():
            return (f"File does not exist: {path}",)
        media_type = _media_type(path)
        if definition.max_bytes is not None and path.stat().st_size > definition.max_bytes:
            problems.append(f"File exceeds {definition.max_bytes // 1_000_000} MB")
        if media_type == "image":
            info = inspect_creative_image(path)
            accepted = {"PNG"} if definition.png_only else {"PNG", "JPEG", "JPG"}
            if info["format"] not in accepted:
                problems.append("Image must be PNG" if definition.png_only else "Image must be PNG or JPEG")
            if path.suffix.lower() not in ({".png"} if definition.png_only else {".png", ".jpg", ".jpeg"}):
                problems.append("Exported image extension must match a supported PNG or JPEG format")
            expected_formats = {".png": {"PNG"}, ".jpg": {"JPEG", "JPG"}, ".jpeg": {"JPEG", "JPG"}}
            if path.suffix.lower() in expected_formats and info["format"] not in expected_formats[path.suffix.lower()]:
                problems.append("Image content does not match its filename extension")
            if info["alpha"]:
                problems.append("Image must not have an alpha channel")
        else:
            if not definition.video:
                return tuple(problems + [f"{profile} supports images only; universal video is unavailable"])
            info = inspect_creative_video(path)
            if not any(part in {"mov", "mp4", "m4v"} for part in info["format"].split(",")):
                problems.append("Video container must be MOV, M4V or MP4")
            if info["duration"] < definition.min_duration or info["duration"] > 30.001:
                problems.append(f"Video duration must be {definition.min_duration}–30 seconds; "
                                f"got {info['duration']:.3f}")
            if not any(abs(info["fps"] - rate) < 0.01 for rate in (30, 60)):
                problems.append(f"Video frame rate must be 30 or 60 fps; got {info['fps']:.3f}")
        problems.extend(_dimension_problems(info["width"], info["height"], definition))
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
        problems.append(str(exc))
    return tuple(problems)


def check_creative_assets(source, profile):
    """Print validation diagnostics and return 0 on success, 1 on any failure."""
    try:
        profiles = _profiles(profile)
        files = discover_creative_sources(source, exclude_generated=False)
        if not files:
            raise ValueError(f"No creative images or videos found: {source}")
        failed = 0
        for path in files:
            candidates = [name for name in profiles
                          if _media_type(path) == "image" or CREATIVE_PROFILES[name].video]
            if not candidates:
                candidates = profiles
            results = [(name, validate_creative_file(path, name)) for name in candidates]
            # In creative-all check mode an existing export need match one profile.
            valid = next((name for name, problems in results if not problems), None)
            if valid is not None:
                print(f"PASS {path} ({valid})")
            else:
                failed += 1
                for name, problems in results:
                    print(f"FAIL {path} ({name}): {'; '.join(problems)}")
        print(f"Creative validation: {len(files) - failed} passed, {failed} failed")
        return int(bool(failed))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Creative validation failed: {exc}")
        return 1


def _background(value):
    value = str(value).strip()
    if not value.startswith("#"):
        value = "#" + value
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        value = "#" + "".join(char * 2 for char in value[1:])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Creative background must be one hex colour, such as #060914")
    return value.upper()


def load_creative_design(path):
    """Read a repeatable composition, resolving its icon beside the design file."""
    path = Path(path).expanduser().resolve()
    design = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(design, dict):
        raise ValueError("Design JSON must be an object")
    for name in ("app_name", "title"):
        if not isinstance(design.get(name), str) or not design[name].strip():
            raise ValueError(f"Design requires a nonempty {name}")
    for field in ("icon", "frame_assets", "frames_bin"):
        if design.get(field):
            if not isinstance(design[field], str):
                raise ValueError(f"Design {field} must be a file path")
            expanded = os.path.expandvars(design[field])
            value = Path(expanded).expanduser()
            if field != "frames_bin" or value.is_absolute() or "/" in expanded:
                design[field] = str(value if value.is_absolute() else path.parent / value)
    return design


def build_creative_image_command(source, output, profile, fit="contain", background="#060914"):
    definition = _profile(profile)
    if fit not in {"contain", "cover"}:
        raise ValueError("Creative fit must be contain or cover")
    size = f"{definition.width}x{definition.height}"
    return ["magick", f"{Path(source).resolve()}[0]", "-auto-orient", "-background", _background(background),
            "-alpha", "remove", "-alpha", "off", "-resize", size + ("^" if fit == "cover" else ""),
            "-gravity", "center", "-extent", size, "+repage", "-colorspace", "sRGB", "-strip",
            f"PNG24:{Path(output).resolve()}"]


def build_creative_video_command(source, output, profile, fit="contain", background="#060914",
                                 fps=30, duration=30):
    definition = _profile(profile)
    if not definition.video:
        raise ValueError("Universal creative assets support images only")
    if fit not in {"contain", "cover"}:
        raise ValueError("Creative fit must be contain or cover")
    if fps not in (30, 60):
        raise ValueError("Creative video frame rate must be 30 or 60")
    width, height = definition.width, definition.height
    colour = _background(background).replace("#", "0x")
    mode = "decrease" if fit == "contain" else "increase"
    scale = f"scale={width}:{height}:force_original_aspect_ratio={mode}:force_divisible_by=2"
    composition = (f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={colour}" if fit == "contain"
                   else f"crop={width}:{height}:(iw-ow)/2:(ih-oh)/2")
    filters = f"{scale},{composition},setsar=1,fps={fps},format=yuv420p"
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(Path(source).resolve()),
            "-map", "0:v:0", "-an", "-t", f"{duration:.6f}", "-vf", filters,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(Path(output).resolve())]


def _output_stem(path, source):
    relative = path.relative_to(source) if source.is_dir() else Path(path.name)
    digest = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:12]
    return f"{path.stem}-{digest}"


def _write_creative_reviews(root, entries):
    upload = {"locales": {}, "creative_assets": entries}
    (root / "asc_upload.json").write_text(json.dumps(upload, indent=2) + "\n", encoding="utf-8")
    (root / "asc_creative_review.json").write_text(
        json.dumps({"creative_assets": entries}, indent=2) + "\n", encoding="utf-8")
    cards = []
    # Manifests record final absolute paths; only their profile/filename is needed here.
    for entry in entries:
        relative = Path(entry["profile"]) / Path(entry["path"]).name
        url = html.escape(quote(relative.as_posix()), quote=True)
        label = html.escape(f"{entry['profile']} · {entry['locale']} · {entry['width']}×{entry['height']}")
        if entry["media_type"] == "video":
            poster = html.escape(quote((Path(entry["profile"]) / Path(entry["poster_path"]).name).as_posix()), quote=True)
            media = f'<video controls preload="metadata" poster="{poster}" src="{url}"></video>'
        else:
            media = f'<img src="{url}" alt="{label}" loading="lazy">'
        cards.append(f'<figure>{media}<figcaption>{label}<br><a href="{url}">{html.escape(relative.name)}</a>'
                     '</figcaption></figure>')
    document = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>App Store creative assets</title><style>'
                'body{font:16px system-ui,sans-serif;background:#111827;color:#f3f4f6;margin:2rem}'
                'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.5rem}'
                'figure{margin:0;padding:1rem;background:#1f2937;border-radius:12px}'
                'img,video{width:100%;height:320px;object-fit:contain;background:#060914}'
                'figcaption{padding-top:1rem;overflow-wrap:anywhere}a{color:#93c5fd}'
                '</style><h1>App Store creative assets</h1><main>' + "".join(cards) + '</main></html>')
    (root / "asc_creative_review.html").write_text(document, encoding="utf-8")


def process_creative_assets(source, output_root, profile, fit="contain", background="#060914",
                            fps=30, max_duration=30, poster_time=0, locale=None, design=None):
    """Export local media and manifests; return final asset paths, excluding posters.

    Images use opaque PNG. Videos use silent H.264 MP4 with an opaque PNG poster.
    ``creative-all`` exports all five image profiles and four video profiles.
    A video shorter than a selected profile's minimum is rejected before rendering.
    """
    profiles = _profiles(profile)
    source = Path(source).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    background = _background(background)
    max_duration = float(max_duration)
    poster_time = float(poster_time)
    if fit not in {"contain", "cover"}:
        raise ValueError("Creative fit must be contain or cover")
    if fps not in (30, 60):
        raise ValueError("Creative video frame rate must be 30 or 60")
    if not math.isfinite(max_duration) or not 0 < max_duration <= 30:
        raise ValueError("Creative maximum duration must be greater than 0 and at most 30 seconds")
    if not math.isfinite(poster_time) or poster_time < 0:
        raise ValueError("Creative poster time must be a nonnegative number of seconds")
    files = discover_creative_sources(source, output_root)
    if not files:
        raise ValueError(f"No creative images or videos found: {source}")
    if design is not None:
        if not isinstance(design, dict):
            raise ValueError("Creative design must be an object")
        if any(_media_type(path) != "image" for path in files):
            raise ValueError("Composed designs currently accept image sources; use a separate run for videos")
    jobs = []
    for path in files:
        media_type = _media_type(path)
        names = [name for name in profiles if media_type == "image" or CREATIVE_PROFILES[name].video]
        if not names:
            raise ValueError(f"{profile} supports images only: {path}")
        duration = None
        if media_type == "video":
            duration = min(inspect_creative_video(path)["duration"], max_duration)
            minimum = max(CREATIVE_PROFILES[name].min_duration for name in names)
            if duration < minimum:
                raise ValueError(f"{path}: selected profiles need at least {minimum} seconds; "
                                 f"available duration is {duration:.3f} seconds")
            if poster_time >= duration:
                raise ValueError(f"Poster time {poster_time} must be before output duration {duration:.3f}")
        for name in names:
            jobs.append((path, media_type, name, duration))
    # A pre-existing profile-directory symlink must not redirect publication into
    # source captures or another directory outside the explicitly selected root.
    input_paths = {path.resolve() for path in files}
    for path, media_type, name, duration in jobs:
        if (output_root / name).is_symlink():
            raise ValueError("Creative output would overlap source or other assets through a "
                             f"profile-directory symlink: {output_root / name}")
        stem = _output_stem(path, source)
        filenames = [stem + (".png" if media_type == "image" else ".mp4")]
        if media_type == "video":
            filenames.append(stem + "-poster.png")
        for filename in filenames:
            destination = (output_root / name / filename).resolve()
            if not destination.is_relative_to(output_root) or destination in input_paths:
                raise ValueError(f"Creative output would overlap source or leave the output directory: {destination}")
    output_root.mkdir(parents=True, exist_ok=True)
    entries = []
    outputs = []
    # Keep failed renders separate from a previously successful output set.
    with TemporaryDirectory(prefix=".creative-stage-", dir=output_root) as staging:
        staging = Path(staging)
        staged_files = []
        for path, media_type, name, duration in jobs:
            definition = CREATIVE_PROFILES[name]
            relative = Path(name) / (_output_stem(path, source) + (".png" if media_type == "image" else ".mp4"))
            temporary = staging / relative
            temporary.parent.mkdir(parents=True, exist_ok=True)
            final = output_root / relative
            entry = {"profile": name, "path": str(final), "media_type": media_type,
                     "locale": locale or "default", "placements": list(definition.placements),
                     "width": definition.width, "height": definition.height, "source": str(path)}
            if media_type == "image":
                if design is None:
                    _run(build_creative_image_command(path, temporary, name, fit, background))
                else:
                    from asc_design import render_design
                    entry["design"] = render_design(path, temporary, (definition.width, definition.height), design)
                    entry["design"]["output"] = str(final)
            else:
                _run(build_creative_video_command(path, temporary, name, fit, background, fps, duration))
                poster_relative = relative.with_name(relative.stem + "-poster.png")
                poster = staging / poster_relative
                _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(poster_time),
                      "-i", str(temporary), "-frames:v", "1", "-pix_fmt", "rgb24", str(poster)])
                poster_problems = validate_creative_file(poster, name)
                if poster_problems:
                    raise RuntimeError(f"Poster validation failed for {path} ({name}): {'; '.join(poster_problems)}")
                entry.update({"poster_path": str(output_root / poster_relative),
                              "poster_time": poster_time, "duration": duration, "fps": fps})
                staged_files.append((poster, output_root / poster_relative))
            problems = validate_creative_file(temporary, name)
            if problems:
                raise RuntimeError(f"Creative validation failed for {path} ({name}): {'; '.join(problems)}")
            entries.append(entry)
            outputs.append(final)
            staged_files.append((temporary, final))
        _write_creative_reviews(staging, entries)
        for temporary, final in staged_files:
            final.parent.mkdir(parents=True, exist_ok=True)
            temporary.replace(final)
        for filename in ("asc_upload.json", "asc_creative_review.json", "asc_creative_review.html"):
            (staging / filename).replace(output_root / filename)
    return outputs
