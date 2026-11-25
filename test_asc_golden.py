"""Opt-in golden-image regression check for the real rendering path.

Renders a fixed, synthetic fixture set through asc_screens.py with the real tools
(ImageMagick, Apple Frames, the Swift/AppKit Mac renderer) and compares each output
with a committed reference in tests/golden/references/.

    ASC_GOLDEN=1 python3 -m unittest test_asc_golden -v          # check
    ASC_GOLDEN=1 ASC_GOLDEN_UPDATE=1 python3 -m unittest test_asc_golden -v   # rewrite references

Environment:
    ASC_GOLDEN            1 to run; anything else skips the whole module.
    ASC_GOLDEN_UPDATE     1 to rewrite the references from the current render.
    ASC_GOLDEN_OUT        folder for failure artefacts (actual and diff images).
                          Default: <system temp>/asc-screens-golden. A folder inside this
                          checkout is ignored (with a note) so a check never dirties the repo.
    ASC_SCREENS_FRAMES_BIN  Apple Frames CLI, as for the tool itself.

How the comparison works: the full-size output must pass the screenshot validator (opaque,
an App Store size) and have the exact expected pixel size, then a
copy scaled to SCALE_PERCENT is compared with the reference by two measures (see
COMPARE_NOTES). References are the scaled copies, which keeps them small. The
references describe one macOS, font, ImageMagick and Apple Frames combination; when a
deliberate change or an OS upgrade moves them, inspect the diffs and rewrite them.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from asc_screens import default_font, find_frames_bin, image_size, validate_screenshot_file

ROOT = Path(__file__).resolve().parent
GOLDEN_DIR = ROOT / "tests" / "golden"
REFERENCE_DIR = GOLDEN_DIR / "references"
SPEC = json.loads((GOLDEN_DIR / "cases.json").read_text(encoding="utf-8"))

ENABLED = os.environ.get("ASC_GOLDEN") == "1"
UPDATE = os.environ.get("ASC_GOLDEN_UPDATE") == "1"

# Compared copy: 25% of the output (330x717 for an iPhone, 720x450 for a Mac screenshot).
SCALE_PERCENT = 25
# Pixels whose colour differs from the reference by more than this (magick -fuzz) count as changed.
PIXEL_FUZZ = "6%"
# Largest tolerated share of changed pixels. Calibrated on the references:
# a 0.6-sigma blur (anti-aliasing and resampling noise) changes 0.2-0.3%, a 1 px shift of the 25% copy
# (4 px in the full image) 0.5-1.4%, and a window moved 40 px, a missing menu bar or Dock, or a dropped
# caption 1.5% and more. The same render on the same machine is pixel-identical (0%).
MAX_CHANGED_FRACTION = 0.004
# Largest tolerated DSSIM (structural dissimilarity, 0 = identical) over the whole image: catches
# broad degradation the changed-pixel share can miss. A +3% hue shift scores 0.0014, a 0.6-sigma blur
# 0.005-0.006, JPEG quality 85 about 0.011, a 1 px shift 0.02-0.04, the deliberate breakages 0.035 and more.
MAX_DSSIM = 0.01
COMPARE_NOTES = (
    f"changed-pixel share <= {MAX_CHANGED_FRACTION} at {PIXEL_FUZZ} fuzz and DSSIM <= {MAX_DSSIM}, "
    f"both on the {SCALE_PERCENT}% copy"
)

RENDER_TIMEOUT = 600
TOOL_TIMEOUT = 120
# Longest wait for pipes and the child to settle after a timeout kill.
KILL_GRACE = 5


def failure_dir():
    """Where failure images go: ASC_GOLDEN_OUT, unless it points into this checkout, then the temp default."""
    default = Path(tempfile.gettempdir()) / "asc-screens-golden"
    value = os.environ.get("ASC_GOLDEN_OUT")
    if not value:
        return default
    path = Path(value).expanduser().resolve()
    if path == ROOT or path.is_relative_to(ROOT):
        print(f"ASC_GOLDEN_OUT={value} is inside the checkout; writing failure images to {default} instead",
              file=sys.stderr)
        return default
    return path


def kill_group(proc):
    """SIGKILL the child's process group; fall back to the child itself if the group kill fails."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def _text(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def run_bounded(command, timeout, **kwargs):
    """subprocess.run that kills the whole process group on timeout (a stuck swift or frames child
    holding the pipes would otherwise keep run() waiting past its timeout). Raises TimeoutExpired.
    Recovery is bounded too: the pipe drain after the kill waits at most KILL_GRACE seconds."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True, **kwargs)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(proc)
            try:
                stdout, stderr = proc.communicate(timeout=KILL_GRACE)
            except subprocess.TimeoutExpired as late:
                # Something still holds a pipe open; keep what was read and move on.
                stdout, stderr = _text(late.stdout), _text(late.stderr)
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
    finally:
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
        try:
            proc.wait(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired:
            pass


def probe_frames(frames):
    """None when the Apple Frames CLI and its device assets work, otherwise the reason."""
    try:
        result = run_bounded([str(frames), "doctor"], TOOL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"{frames} doctor timed out after {TOOL_TIMEOUT}s"
    except OSError as exc:
        return f"{frames} cannot start: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return f"{frames} doctor failed: {detail[-1] if detail else result.returncode}"
    return None


def probe_xcode():
    """None when the Xcode Command Line Tools are installed, otherwise the reason."""
    try:
        result = run_bounded(["xcode-select", "-p"], TOOL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"xcode-select -p timed out after {TOOL_TIMEOUT}s"
    except OSError as exc:
        return f"xcode-select cannot start: {exc}"
    if result.returncode != 0:
        return "Swift needs the Xcode Command Line Tools: xcode-select --install"
    return None


def skip_reason():
    if not ENABLED:
        return "golden-image check is opt-in: set ASC_GOLDEN=1"
    if sys.platform != "darwin":
        return "golden references are macOS renders (AppKit, system fonts)"
    for tool in ("magick", "swift"):
        if not shutil.which(tool):
            return f"{tool} not found on PATH"
    reason = probe_xcode()
    if reason:
        return reason
    if not default_font():
        return "the caption font (Arial) is missing from this Mac"
    frames = find_frames_bin()
    if frames is None:
        return "Apple Frames CLI not found: put frames on PATH or set ASC_SCREENS_FRAMES_BIN"
    return probe_frames(frames)


SKIP_REASON = skip_reason()


def magick(*args, timeout=TOOL_TIMEOUT):
    return subprocess.run(["magick", *map(str, args)], check=True, capture_output=True, text=True, timeout=timeout)


def png24(path):
    return f"PNG24:{path}"


def make_capture(path, size, label, font):
    """A synthetic app capture: gradient, cards, a circle and plain ASCII text, asymmetric on purpose."""
    width, height = size
    unit = width / 100
    cards = []
    for index, shade in enumerate(("#FFFFFF", "#E7EEFF", "#DDF7F3")):
        top = round(height * (0.30 + 0.17 * index))
        cards += ["-fill", shade, "-draw",
                  f"roundrectangle {round(unit * 7)},{top} {round(unit * (45 + 12 * index))},{top + round(height * 0.13)} "
                  f"{round(unit * 3)},{round(unit * 3)}"]
    magick(
        "-size", f"{width}x{height}", "gradient:#1B2A5E-#0E8F8A",
        *cards,
        "-fill", "#F5A623", "-draw", f"circle {round(width * 0.78)},{round(height * 0.22)} "
                                     f"{round(width * 0.78 + unit * 9)},{round(height * 0.22)}",
        "-fill", "#FFFFFF", "-font", font, "-pointsize", round(unit * 7), "-gravity", "NorthWest",
        "-annotate", f"+{round(unit * 7)}+{round(height * 0.12)}", label,
        "-fill", "#0A1330", "-pointsize", round(unit * 3.2), "-gravity", "SouthEast",
        "-annotate", f"+{round(unit * 5)}+{round(height * 0.04)}", "SYNTHETIC FIXTURE 12:34",
        "-alpha", "off", png24(path),
    )


def make_icon(path, top, bottom, mark, font):
    """A full-bleed square icon (no transparent corners), so the renderer applies the macOS icon shape."""
    magick(
        "-size", "512x512", f"gradient:{top}-{bottom}",
        "-fill", "#FFFFFF", "-font", font, "-pointsize", 300, "-gravity", "center", "-annotate", "+0+0", mark,
        "-alpha", "off", png24(path),
    )


def make_wallpaper(path):
    magick("-size", "3456x2234", "gradient:#202B4D-#4A2F63", "-fill", "#6C8CFF40", "-draw",
           "circle 2600,500 3300,500", "-alpha", "off", png24(path))


def metric_output(*args):
    """Run `magick compare`; its exit code 1 only means the images differ, the metric is on stderr."""
    result = subprocess.run(["magick", "compare", *map(str, args)], capture_output=True, text=True, timeout=TOOL_TIMEOUT)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"magick compare failed ({result.returncode}): {result.stderr.strip()}")
    # ImageMagick 7 prints "<raw> (<normalised 0..1>)"; for AE the normalised value is the changed-pixel share.
    found = re.findall(r"\(([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\)", result.stderr)
    if not found:
        raise RuntimeError(f"magick compare printed no normalised metric: {result.stderr!r}")
    return float(found[-1])  # the metric comes last; earlier lines may be warnings


def measure(actual_small, reference, diff_path):
    """(changed-pixel share, DSSIM) of two same-sized images; writes a highlighted diff image."""
    changed = metric_output("-metric", "AE", "-fuzz", PIXEL_FUZZ, actual_small, reference, diff_path)
    dssim = metric_output("-metric", "DSSIM", actual_small, reference, "null:")
    return changed, dssim


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class GoldenRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = str(find_frames_bin())
        cls.font = default_font()
        cls.work = Path(tempfile.mkdtemp(prefix="asc-golden-"))
        cls.addClassCleanup(shutil.rmtree, cls.work, ignore_errors=True)
        cls.assets = cls.work / "assets"
        cls.assets.mkdir()
        make_wallpaper(cls.assets / "wallpaper.png")
        make_icon(cls.assets / "app.png", "#FF7A45", "#C2255C", "S", cls.font)
        docks = []
        for name, top, bottom, mark in (("a", "#3B82F6", "#1E3A8A", "A"), ("b", "#22C55E", "#166534", "B"),
                                        ("c", "#FACC15", "#A16207", "C")):
            make_icon(cls.assets / f"dock-{name}.png", top, bottom, mark, cls.font)
            docks.append(str(cls.assets / f"dock-{name}.png"))
        cls.dock = ",".join(docks)
        cls.copy_file = cls.work / "copy.json"
        cls.copy_file.write_text(json.dumps(SPEC["copy"]), encoding="utf-8")
        if UPDATE:
            REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    def render(self, case):
        """Run asc_screens.py on one generated capture; returns the output image path."""
        source = self.work / case["name"] / "source" / case["device"]
        source.mkdir(parents=True)
        make_capture(source / f"{case['label']}.png", case["capture"], case["label"], self.font)
        out_root = self.work / case["name"] / "out"
        args = [str(self.copy_file) if arg == "@copy" else arg for arg in case["args"]]
        command = [
            sys.executable, str(ROOT / "asc_screens.py"), str(source.parent),
            "--output-root", str(out_root), "--background", SPEC["background"],
            "--frames-bin", self.frames, "--frame-color", "Silver", *args,
        ]
        if case["device"] == "mac":
            command += ["--mac-app", str(self.assets / "app.png"), "--mac-app-name", SPEC["mac_app_name"],
                        "--mac-menus", SPEC["mac_menus"], "--mac-wallpaper", str(self.assets / "wallpaper.png"),
                        "--mac-clock", SPEC["mac_clock"], "--mac-dock", self.dock]
        try:
            result = run_bounded(command, RENDER_TIMEOUT, cwd=ROOT, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            self.fail(f"{case['name']}: render timed out after {RENDER_TIMEOUT}s "
                      f"(a stuck Apple Frames or Swift step?)\n{(exc.stderr or '')[-1500:]}")
        if result.returncode != 0:
            self.fail(f"{case['name']}: asc_screens.py exited {result.returncode}\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}")
        output = out_root / case["output"]
        if not output.is_file():
            self.fail(f"{case['name']}: expected output {case['output']} is missing\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}")
        return output

    def check_case(self, case):
        output = self.render(case)
        # Validate the full-size output first: normalising below strips alpha, so a transparent
        # render would otherwise pass. This also guards references written in update mode.
        report = validate_screenshot_file(output, case["device"])
        self.assertTrue(report.ok, f"{case['name']}: output fails screenshot validation: {'; '.join(report.problems)}")
        expected_size = tuple(case["size"])
        self.assertEqual(image_size(output), expected_size, f"{case['name']}: output pixel size")

        small = self.work / f"{case['name']}-actual.png"
        magick(output, "-resize", f"{SCALE_PERCENT}%", "-alpha", "off", "-strip", png24(small))
        reference = REFERENCE_DIR / f"{case['name']}.png"
        if UPDATE:
            shutil.copyfile(small, reference)
            return
        if not reference.is_file():
            self.fail(f"{case['name']}: no reference at {reference}; create it with ASC_GOLDEN_UPDATE=1")
        self.assertEqual(image_size(small), image_size(reference),
                         f"{case['name']}: scaled size differs from the reference; the output size changed")

        out_dir = failure_dir()
        diff = self.work / f"{case['name']}-diff.png"
        changed, dssim = measure(small, reference, diff)
        print(f"\n  {case['name']}: changed pixels {changed:.4%}, DSSIM {dssim:.5f}", file=sys.stderr)
        if changed > MAX_CHANGED_FRACTION or dssim > MAX_DSSIM:
            out_dir.mkdir(parents=True, exist_ok=True)
            kept = {}
            for label, path in (("actual", small), ("reference", reference), ("diff", diff), ("full", output)):
                kept[label] = out_dir / f"{case['name']}-{label}.png"
                shutil.copyfile(path, kept[label])
            self.fail(
                f"{case['name']}: differs from the golden reference "
                f"(changed pixels {changed:.4%}, limit {MAX_CHANGED_FRACTION:.2%}; DSSIM {dssim:.5f}, limit {MAX_DSSIM})\n"
                + "\n".join(f"  {label}: {path}" for label, path in kept.items())
                + f"\n  rule: {COMPARE_NOTES}\n  If the change is intended, rewrite with ASC_GOLDEN_UPDATE=1."
            )


def _add_case_tests():
    for case in SPEC["cases"]:
        def test(self, case=case):
            self.check_case(case)
        test.__name__ = f"test_{case['name'].replace('-', '_')}"
        setattr(GoldenRenderTests, test.__name__, test)


_add_case_tests()


if __name__ == "__main__":
    unittest.main()
