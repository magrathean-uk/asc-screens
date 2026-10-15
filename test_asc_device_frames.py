"""Pixel-level checks for the local device framing boundary."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import asc_device_frames as frames


_FAKE_FRAMES = r'''
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
if os.environ.get("FRAMES_ASSETS") == "missing-test-assets" or "missing-test-assets" in args:
    print("Frames assets not found: missing-test-assets", file=sys.stderr)
    sys.exit(1)
source = pathlib.Path(args[-1])
w, h = map(int, subprocess.check_output(["magick", str(source), "-format", "%w %h", "info:"], text=True).split())
phone = w in (1320, 2868)
pad = (w, h) in ((2064, 2752), (2752, 2064))
device = "iPhone 17 Pro Max Portrait" if phone else "iPad Pro 2024 13 Portrait" if pad else None
if "info" in args:
    info = dict(width=w, height=h, device=device, colors=["Deep Blue", "Silver"] if phone else [],
                variants=[device] if device else [], x="24", y="36", has_mask=phone)
    if not device:
        info["error"] = "Unknown device (width %dpx)" % w
    print(json.dumps(info))
elif "frame" in args:
    output = pathlib.Path(args[args.index("--output") + 1]) / "capture_framed.png"
    color = args[args.index("--colors") + 1] if "--colors" in args else None
    # Deliberately asymmetric, distinctive frame. Pixel checks prove the CLI's
    # own bitmap survives and the source is placed without clipping/stretching.
    subprocess.run(["magick", "-size", "%dx%d" % (w+64, h+80), "xc:#222222",
                    "-fill", "#00FF00", "-draw", "rectangle 0,0 15,25",
                    str(source), "-geometry", "+24+36", "-composite", str(output)], check=True)
    print(json.dumps(dict(device=device, color=color, dimensions="%dx%d" % (w,h),
                          frame_size="%dx%d" % (w+64,h+80), masked=phone,
                          mask_missing=False, output=str(output))))
'''


@unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
class DeviceFramePixelTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cli = self.root / "frames-test"
        self.cli.write_text(f"#!{sys.executable}\n" + _FAKE_FRAMES)
        self.cli.chmod(0o700)
        self.design = {"frames_bin": str(self.cli)}

    def tearDown(self):
        self.temp.cleanup()

    def image(self, size, name="source.png"):
        source = self.root / name
        width, height = size
        subprocess.run(["magick", "-size", f"{width}x{height}", "xc:white", "-fill", "red",
                        "-draw", f"rectangle 0,100 9,{height-100}", "-fill", "blue",
                        "-draw", f"rectangle {width-10},100 {width-1},{height-100}",
                        "-fill", "#FF00FF", "-draw",
                        f"circle {width//2},{height//2} {width//2+100},{height//2}", str(source)], check=True)
        return source

    def rgb(self, path, x, y):
        value = subprocess.check_output(["magick", str(path), "-format",
            f"%[fx:round(255*p{{{x},{y}}}.r)] %[fx:round(255*p{{{x},{y}}}.g)] %[fx:round(255*p{{{x},{y}}}.b)]", "info:"], text=True)
        return tuple(map(int, value.split()))

    def test_scaled_capture_keeps_both_edges_and_round_landmark(self):
        source = self.image((980, 2130))
        original = source.read_bytes()
        output, metadata = frames.render_device_frame(source, self.root / "out", "iphone", self.design)
        self.assertEqual(metadata["provider"], "Apple Frames")
        self.assertEqual(metadata["panel_size"], [1320, 2868])
        self.assertEqual(metadata["framed_size"], [1384, 2948])
        self.assertEqual(metadata["color"], "Silver")
        self.assertTrue(metadata["normalized"])
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(self.rgb(output, 5, 5), (0, 255, 0))
        # Both original edges survive containment; cover-cropping loses them.
        self.assertEqual(self.rgb(output, 28, 600), (255, 0, 0))
        self.assertEqual(self.rgb(output, 1338, 600), (0, 0, 255))
        # A round source feature must stay round after the proportional resize.
        result = subprocess.check_output(["magick", str(output), "-alpha", "off", "-fill", "black",
            "+opaque", "#FF00FF", "-fill", "white", "-opaque", "#FF00FF", "-trim", "-format", "%w %h", "info:"], text=True)
        width, height = map(int, result.split())
        self.assertLessEqual(abs(width-height), 2)

    def test_width_only_frames_match_is_not_accepted_as_native_panel(self):
        source = self.image((1320, 1600))
        output, metadata = frames.render_device_frame(source, self.root / "out", "iphone", self.design)
        self.assertEqual(metadata["panel_size"], [1320, 2868])
        self.assertTrue(metadata["normalized"])
        # Its top/bottom letterbox is preserved, rather than stretching 1600px
        # of content over the entire 2868px panel or clipping the source.
        self.assertEqual(self.rgb(output, 200, 60), (0, 0, 0))

    def test_native_ipad_matches_without_letterboxing_or_color(self):
        source = self.image((2064, 2752))
        output, metadata = frames.render_device_frame(source, self.root / "out", "ipad", self.design)
        self.assertEqual(metadata["panel_size"], [2064, 2752])
        self.assertFalse(metadata["normalized"])
        self.assertIsNone(metadata["color"])
        self.assertEqual(self.rgb(output, 28, 600), (255, 0, 0))
        self.assertEqual(self.rgb(output, 2080, 600), (0, 0, 255))

    def test_missing_assets_error_does_not_trigger_normalization_or_fake_frame(self):
        source = self.image((980, 2130))
        output = self.root / "out"
        with patch.dict("os.environ", {"FRAMES_ASSETS": "missing-test-assets"}):
            with self.assertRaisesRegex(RuntimeError, "Frames assets not found"):
                frames.render_device_frame(source, output, "iphone", self.design)
        self.assertFalse(output.exists())

    def test_explicit_incompatible_model_or_color_is_rejected(self):
        source = self.image((1320, 2868))
        for field, value, message in (("frame_device", "iPad Pro", "incompatible"),
                                      ("frame_color", "random", "unavailable")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                frames.render_device_frame(source, self.root / "out", "iphone", dict(self.design, **{field:value}))


class DeviceFrameBoundaryTests(unittest.TestCase):
    def test_missing_cli_has_actionable_error_without_fake_bezel(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            source.write_bytes(b"source")
            def run(command):
                if command[0] == "magick":
                    return subprocess.CompletedProcess(command, 0, "1320 2868", "")
                raise FileNotFoundError(command[0])
            with self.assertRaisesRegex(RuntimeError, "Apple Frames CLI"):
                frames.render_device_frame(source, root / "out", "iphone", runner=run)
            self.assertFalse((root / "out").exists())

    def test_receipt_cannot_point_to_an_unowned_image(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            source.write_bytes(b"source")
            def run(command):
                if command[0] == "magick":
                    return subprocess.CompletedProcess(command, 0, "1320 2868", "")
                info = {"device":"iPhone 17 Pro Max Portrait", "colors":[], "x":"24", "y":"36"}
                if "frame" in command:
                    info.update(color=None, masked=True, mask_missing=False, dimensions="1320x2868", output=str(source))
                return subprocess.CompletedProcess(command, 0, json.dumps(info), "")
            with self.assertRaisesRegex(RuntimeError, "owned rendering directory"):
                frames.render_device_frame(source, root / "out", "iphone", runner=run)


if __name__ == "__main__":
    unittest.main()
