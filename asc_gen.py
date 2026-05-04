#!/usr/bin/env python3
import shutil
from argparse import Namespace
from pathlib import Path

from asc_screens import (
    collect_jobs,
    process_kind,
    resolve_background_palette,
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
    aliases = {"i": "iphone", "phone": "iphone", "p": "ipad", "pad": "ipad"}
    value = aliases.get(value, value)
    if value in {"iphone", "ipad"}:
        return [value]
    raise ValueError("Choose iphone, ipad, or both")


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
            return choose_kinds(ask("2. iphone, ipad, or both", auto_text), jobs)
        except ValueError as exc:
            print(exc)


def prompt_background():
    while True:
        background = ask("3. Colour theme hex codes, comma separated. Enter for default", "")
        try:
            if background:
                return resolve_background_palette(background)
            return resolve_background_palette(theme="teslatlas")
        except ValueError as exc:
            print(f"Bad colour: {exc}")


def main():
    source = Path(ask("1. Source folder", ".")).expanduser()
    if not source.is_dir():
        raise SystemExit(f"Source folder not found: {source}")

    jobs = collect_jobs(source)
    if not jobs:
        raise SystemExit("No screenshots found. Use PNG, JPG, JPEG, HEIC, HEIF, TIF, or TIFF.")

    counts = count_by_kind(jobs)
    print(f"Found {len(jobs)} screenshots: {counts['iphone']} iphone, {counts['ipad']} ipad")
    kinds = prompt_kinds(jobs)
    background_colors = prompt_background()

    output_root = ask("4. Output folder", "asc_out")
    print(f"Output: {output_root}")
    print(f"Theme: {', '.join(background_colors)}")
    args = Namespace(
        output_root=output_root,
        frames_bin=str(find_frames_bin()),
        frame_color="Silver",
        validate=True,
    )

    total = 0
    for kind in kinds:
        total += len(process_kind(args, jobs, kind, background_colors))
    print(f"Done: {total} screenshots")


if __name__ == "__main__":
    main()
