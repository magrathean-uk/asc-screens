#!/usr/bin/env python3
from argparse import Namespace
from pathlib import Path
import subprocess

from asc_creative import (
    CREATIVE_PROFILES, VIDEO_EXTENSIONS, check_creative_assets, load_creative_design,
    discover_creative_sources, process_creative_assets,
)

from asc_screens import (
    collect_jobs,
    process_kind,
    require_frames_bin,
    resolve_background_palette,
    resolve_localized_builds,
    validate_existing_images,
    expand_export_targets,
    normalize_hex,
    write_contact_sheet,
    write_review_manifest,
    write_upload_manifest,
)


def detected_kinds(jobs):
    found = {job.device for job in jobs}
    return [kind for kind in ("iphone", "ipad", "mac") if kind in found]


def count_by_kind(jobs):
    return {kind: sum(1 for job in jobs if job.device == kind) for kind in ("iphone", "ipad", "mac")}


def choose_kinds(answer, jobs):
    value = answer.strip().lower()
    if not value:
        kinds = detected_kinds(jobs)
        return kinds or ["iphone", "ipad"]
    if value in {"both", "all", "b"}:
        return ["iphone", "ipad", "mac"]
    if value in {"latest", "l"}:
        return ["iphone-latest", "ipad-latest", "mac-latest"]
    aliases = {"i": "iphone", "phone": "iphone", "p": "ipad", "pad": "ipad", "m": "mac"}
    value = aliases.get(value, value)
    if value in {"iphone", "ipad", "mac", "iphone-latest", "ipad-latest", "mac-latest", "all-latest"}:
        if value == "all-latest":
            return ["iphone-latest", "ipad-latest", "mac-latest"]
        return [value]
    raise ValueError("Choose iphone, ipad, mac, or all")


def choose_validation_mode(answer):
    value = answer.strip().lower()
    aliases = {"": "build", "b": "build", "build": "build", "c": "check", "check": "check"}
    try:
        return aliases[value]
    except KeyError as exc:
        raise ValueError("Choose build or check") from exc


def choose_template(answer):
    value = answer.strip().lower()
    aliases = {"": "plain", "plain": "plain", "top": "title-top", "title-top": "title-top", "bottom": "title-bottom", "title-bottom": "title-bottom"}
    try:
        return aliases[value]
    except KeyError as exc:
        raise ValueError("Choose plain, top, or bottom") from exc


def choose_asset(answer):
    value = answer.strip().lower() or "screenshots"
    if value in {"screenshots", *CREATIVE_PROFILES, "creative-all"}:
        return value
    raise ValueError("Choose screenshots, header, search-results, universal, event-card, event-detail, or creative-all")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def prompt_kinds(jobs):
    auto = detected_kinds(jobs)
    auto_text = "all" if len(auto) > 1 else (auto[0] if auto else "all")
    while True:
        try:
            return choose_kinds(ask("3. iphone, ipad, mac, all, or latest", auto_text), jobs)
        except ValueError as exc:
            print(exc)


def prompt_mode():
    while True:
        try:
            return choose_validation_mode(ask("2. build or check", "build"))
        except ValueError as exc:
            print(exc)


def prompt_background():
    while True:
        background = ask("4. Colour theme hex codes, comma separated. Enter for default", "")
        try:
            if background:
                return resolve_background_palette(background)
            return resolve_background_palette(theme="teslatlas")
        except ValueError as exc:
            print(f"Bad colour: {exc}")


def prompt_template(default="plain"):
    while True:
        try:
            return choose_template(ask("6. template plain, top, or bottom", default))
        except ValueError as exc:
            print(exc)


def prompt_copy_file():
    value = ask("5. copy file json path. Enter for filename titles", "")
    return value or None


def prompt_locale():
    value = ask("7. locale from copy file. Enter for all", "")
    return value or None


def prompt_asset():
    while True:
        try:
            return choose_asset(ask("Asset: screenshots, header, search-results, universal, event-card, event-detail, creative-all", "screenshots"))
        except ValueError as exc:
            print(exc)


def run_creative_guided(source, mode, asset):
    if mode == "check":
        raise SystemExit(check_creative_assets(source, asset))
    design_file = None
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        design_file = ask("Design JSON for composed artwork. Enter to resize existing artwork", "") or None
    try:
        design = load_creative_design(design_file) if design_file else None
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Cannot read design: {exc}") from exc
    fit, background = "contain", "#060914"
    if design is None:
        while True:
            fit = ask("Fit: contain (padding) or cover (center crop)", "contain").lower()
            if fit in {"contain", "cover"}:
                break
            print("Choose contain or cover")
        while True:
            try:
                background = normalize_hex(ask("Padding/background hex colour", "#060914"))
                break
            except ValueError as exc:
                print(exc)
    locale = ask("Asset locale. Enter for default", "") or None
    output_root = ask("Output folder", "asc_out")
    try:
        options = {}
        if any(path.suffix.lower() in VIDEO_EXTENSIONS for path in discover_creative_sources(source, output_root)):
            while True:
                try:
                    fps = int(ask("Video frame rate: 30 or 60", "30"))
                    duration = float(ask("Maximum video duration in seconds (up to 30)", "30"))
                    poster_time = float(ask("Poster time in seconds within the exported video", "0"))
                    if fps not in (30, 60) or not 0 < duration <= 30 or not 0 <= poster_time < duration:
                        raise ValueError("Use 30 or 60 fps, a duration up to 30, and a poster within that duration.")
                    options = {"fps": fps, "max_duration": duration, "poster_time": poster_time}
                    break
                except ValueError as exc:
                    print(exc)
        outputs = process_creative_assets(source, output_root, asset, fit=fit, background=background, locale=locale,
                                         design=design, **options)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Creative export failed: {exc}") from exc
    print(f"Done: {len(outputs)} creative assets; review {Path(output_root) / 'asc_creative_review.html'}")


def main():
    source = Path(ask("1. Source folder or creative artwork/video file", ".")).expanduser()
    if not source.exists():
        raise SystemExit(f"Source not found: {source}")

    mode = prompt_mode()
    asset = prompt_asset()
    if asset != "screenshots":
        run_creative_guided(source, mode, asset)
        return
    if not source.is_dir():
        raise SystemExit("Screenshot mode needs a source folder.")

    jobs = collect_jobs(source)
    if not jobs:
        raise SystemExit("No screenshots found. Use PNG, JPG, JPEG, HEIC, HEIF, TIF, or TIFF.")

    counts = count_by_kind(jobs)
    print(f"Found {len(jobs)} screenshots: {counts['iphone']} iphone, {counts['ipad']} ipad, {counts['mac']} mac")
    if mode == "check":
        raise SystemExit(validate_existing_images(source))

    kinds = prompt_kinds(jobs)
    background_colors = prompt_background()
    copy_file = prompt_copy_file()
    template = prompt_template("top" if not copy_file else "plain")
    locale = prompt_locale() if copy_file else None

    output_root = ask("8. Output folder", "asc_out")
    print(f"Output: {output_root}")
    print(f"Theme: {', '.join(background_colors)}")
    args = Namespace(
        output_root=output_root,
        frames_bin=str(require_frames_bin()),
        frame_color="Silver",
        validate=True,
    )

    total = 0
    outputs = []
    for build_locale, copy in resolve_localized_builds(copy_file, locale):
        scoped_root = Path(output_root) / build_locale if build_locale else Path(output_root)
        scoped_args = Namespace(**vars(args))
        scoped_args.output_root = scoped_root
        for kind in kinds:
            for resolved_kind, target_size in expand_export_targets(kind):
                built = process_kind(scoped_args, jobs, resolved_kind, background_colors, target_size=target_size, template=template, copy=copy)
                outputs.extend(built)
                total += len(built)
    write_review_manifest(output_root, outputs)
    write_contact_sheet(output_root, outputs)
    write_upload_manifest(output_root, outputs)
    print(f"Done: {total} screenshots")


if __name__ == "__main__":
    main()
