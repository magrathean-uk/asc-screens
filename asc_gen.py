#!/usr/bin/env python3
import shutil
from argparse import Namespace
from pathlib import Path

from asc_screens import (
    collect_jobs,
    process_kind,
    resolve_background_palette,
    resolve_localized_builds,
    validate_existing_images,
    expand_export_targets,
    write_contact_sheet,
    write_review_manifest,
    write_upload_manifest,
)


def detected_kinds(jobs):
    found = {job.device for job in jobs}
    return [kind for kind in ("iphone", "ipad") if kind in found]


def count_by_kind(jobs):
    return {kind: sum(1 for job in jobs if job.device == kind) for kind in ("iphone", "ipad")}


def choose_kinds(answer, jobs):
    value = answer.strip().lower()
    if not value:
        kinds = detected_kinds(jobs)
        return kinds or ["iphone", "ipad"]
    if value in {"both", "all", "b"}:
        return ["iphone", "ipad"]
    if value in {"latest", "l"}:
        return ["iphone-latest", "ipad-latest"]
    aliases = {"i": "iphone", "phone": "iphone", "p": "ipad", "pad": "ipad"}
    value = aliases.get(value, value)
    if value in {"iphone", "ipad", "iphone-latest", "ipad-latest", "all-latest"}:
        if value == "all-latest":
            return ["iphone-latest", "ipad-latest"]
        return [value]
    raise ValueError("Choose iphone, ipad, or both")


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


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def find_frames_bin():
    home_bin = Path.home() / ".local/bin/frames"
    if home_bin.exists():
        return home_bin
    found = shutil.which("frames")
    if found:
        return Path(found)
    raise SystemExit("Need Apple Frames CLI at ~/.local/bin/frames or on PATH")


def prompt_kinds(jobs):
    auto = detected_kinds(jobs)
    auto_text = "both" if auto == ["iphone", "ipad"] else (auto[0] if auto else "both")
    while True:
        try:
            return choose_kinds(ask("3. iphone, ipad, both, or latest", auto_text), jobs)
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


def prompt_template():
    while True:
        try:
            return choose_template(ask("5. template plain, top, or bottom", "plain"))
        except ValueError as exc:
            print(exc)


def prompt_copy_file():
    value = ask("6. copy file json path. Enter for none", "")
    return value or None


def prompt_locale():
    value = ask("7. locale from copy file. Enter for all", "")
    return value or None


def main():
    source = Path(ask("1. Source folder", ".")).expanduser()
    if not source.is_dir():
        raise SystemExit(f"Source folder not found: {source}")

    jobs = collect_jobs(source)
    if not jobs:
        raise SystemExit("No screenshots found. Use PNG, JPG, JPEG, HEIC, HEIF, TIF, or TIFF.")

    counts = count_by_kind(jobs)
    print(f"Found {len(jobs)} screenshots: {counts['iphone']} iphone, {counts['ipad']} ipad")
    mode = prompt_mode()
    if mode == "check":
        raise SystemExit(validate_existing_images(source))

    kinds = prompt_kinds(jobs)
    background_colors = prompt_background()
    template = prompt_template()
    copy_file = prompt_copy_file()
    locale = prompt_locale() if copy_file else None

    output_root = ask("8. Output folder", "asc_out")
    print(f"Output: {output_root}")
    print(f"Theme: {', '.join(background_colors)}")
    args = Namespace(
        output_root=output_root,
        frames_bin=str(find_frames_bin()),
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
