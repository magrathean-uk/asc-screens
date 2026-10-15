"""Render evidence for continuous icon-colour gradients and shape-free output."""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from asc_finish import FINISH_VERSION, render_finish


LIGHT = {"background": "#F4F7FC", "ink": "#0F1D34", "muted": "#61728A",
         "stage": "#E6EDF8", "accent": "#2563EB", "line": "#D7E1F0",
         "gradient_colors": ["#234AF5", "#38C9EA"]}
DARK = dict(LIGHT, background="#080F1B", stage="#102238", accent="#54D9AB",
            gradient_colors=["#34B58D", "#92D1C3", "#216785"])
WIDE_STAGE = {"x": 340, "y": 20, "width": 260, "height": 320}
WIDE_SAFE = {"x": 30, "y": 20, "width": 580, "height": 320}


def pixels(path):
    return subprocess.run(["magick", str(path), "-depth", "8", "RGB:-"],
                          check=True, capture_output=True).stdout


def pixel(data, width, x, y):
    index = (y * width + x) * 3
    return tuple(data[index:index + 3])


def difference(first, second):
    return max(abs(a - b) for a, b in zip(first, second))


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


class GraphicFinishInputTests(unittest.TestCase):
    def test_invalid_options_and_geometry_fail_before_running_magick_or_writing(self):
        cases = ({"finish": "neon"}, {"motif": "fake-chart"}, {"stage_radius": float("nan")},
                 {"stage_radius": -1}, {"size": (0, 360)}, {"size": (True, 360)},
                 {"palette": dict(LIGHT, accent="url:remote")},
                 {"palette": dict(LIGHT, gradient_colors=["#234AF5"])},
                 {"palette": dict(LIGHT, gradient_colors="#234AF5")},
                 {"palette": dict(LIGHT, gradient_colors=["#234AF5", "remote:icon"])},
                 {"stage_box": dict(WIDE_STAGE, width=-10)},
                 {"stage_box": dict(WIDE_STAGE, x=float("inf"))},
                 {"stage_box": dict(WIDE_STAGE, x=1000)},
                 {"safe_area": dict(WIDE_SAFE, height=0)})
        with TemporaryDirectory() as temporary:
            for index, overrides in enumerate(cases):
                with self.subTest(overrides=overrides):
                    runner = Mock()
                    parent = Path(temporary) / str(index)
                    args = dict(output=parent / "result.png", size=(640, 360), palette=LIGHT,
                                stage_box=WIDE_STAGE, safe_area=WIDE_SAFE, runner=runner)
                    args.update(overrides)
                    with self.assertRaises(ValueError):
                        render_finish(**args)
                    runner.assert_not_called()
                    self.assertFalse(parent.exists())

    def test_output_requires_png(self):
        runner = Mock()
        with self.assertRaisesRegex(ValueError, "png extension"):
            render_finish("result.jpg", (640, 360), LIGHT, WIDE_STAGE, WIDE_SAFE, runner=runner)
        runner.assert_not_called()


@unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
class GraphicFinishRenderTests(unittest.TestCase):
    def test_flat_is_uniform_over_the_whole_canvas(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "flat.png"
            result = render_finish(output, (640, 360), LIGHT, WIDE_STAGE, WIDE_SAFE,
                                   finish="flat", motif="grid")
            self.assertEqual(pixels(output), bytes(rgb(LIGHT["background"])) * (640 * 360))
            self.assertEqual(result["motif"], "none")
            self.assertEqual(result["motif_paths"], 0)
            self.assertFalse(result["stage_drawn"])
            self.assertEqual(result["gradient_strength"], [0, 0])

    def test_studio_wide_and_portrait_are_smooth_and_quieter_beside_copy(self):
        with TemporaryDirectory() as temporary:
            for size, stage, safe in (
                ((640, 360), WIDE_STAGE, WIDE_SAFE),
                ((360, 640), {"x": 24, "y": 300, "width": 312, "height": 310},
                 {"x": 20, "y": 25, "width": 320, "height": 590}),
            ):
                for name, palette in (("light", LIGHT), ("dark", DARK)):
                    with self.subTest(size=size, palette=name):
                        output = Path(temporary) / f"{name}-{size[0]}.png"
                        result = render_finish(output, size, palette, stage, safe)
                        json.dumps(result)
                        data = pixels(output)
                        self.assertEqual(len(data), size[0] * size[1] * 3)
                        # Colour varies across the canvas, without local panel edges.
                        leading = pixel(data, size[0], size[0] // 10, size[1] // 10)
                        middle = pixel(data, size[0], size[0] // 2, size[1] // 2)
                        trailing = pixel(data, size[0], size[0] * 9 // 10, size[1] * 9 // 10)
                        self.assertGreater(difference(leading, trailing), 8)
                        self.assertNotEqual(leading, middle)
                        self.assertNotEqual(middle, trailing)
                        self.assertLessEqual(difference(leading, rgb(palette["background"])), 9)
                        self.assertGreater(difference(trailing, rgb(palette["background"])),
                                           difference(leading, rgb(palette["background"])))
                        # Scan horizontal/vertical slices, including the former stage
                        # boundary: no adjacent-pixel step from an outline or box.
                        for y in (stage["y"], size[1] // 2, size[1] - 1):
                            for x in range(size[0] - 1):
                                self.assertLessEqual(difference(pixel(data, size[0], x, y),
                                                                pixel(data, size[0], x + 1, y)), 2)
                        for x in (stage["x"], size[0] // 2, size[0] - 1):
                            for y in range(size[1] - 1):
                                self.assertLessEqual(difference(pixel(data, size[0], x, y),
                                                                pixel(data, size[0], x, y + 1)), 2)
                        self.assertFalse(result["stage_drawn"])
                        self.assertEqual(result["gradient_colors"], palette["gradient_colors"])
                        self.assertTrue(result["validated"])

    def test_legacy_motifs_and_stage_geometry_cannot_add_shapes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            plain = root / "plain.png"
            render_finish(plain, (640, 360), LIGHT, WIDE_STAGE, WIDE_SAFE)
            for motif in ("grid", "orbits", "paths", "corners"):
                with self.subTest(motif=motif):
                    output = root / f"{motif}.png"
                    result = render_finish(output, (640, 360), LIGHT,
                                           {"x": 70, "y": 90, "width": 420, "height": 210},
                                           WIDE_SAFE, motif=motif, stage_radius=0)
                    self.assertEqual(plain.read_bytes(), output.read_bytes())
                    self.assertEqual(result["effective_motif"], "none")
                    self.assertEqual(result["motif_paths"], 0)
                    self.assertEqual(result["motif_opacity"], 0)
                    self.assertFalse(result["stage_drawn"])

    def test_changing_icon_colours_changes_the_gradient_without_using_accent(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            blue, warm, accent = (root / name for name in ("blue.png", "warm.png", "accent.png"))
            render_finish(blue, (640, 360), LIGHT, WIDE_STAGE, WIDE_SAFE)
            render_finish(warm, (640, 360), dict(LIGHT, gradient_colors=["#E33D38", "#E9A734"]),
                          WIDE_STAGE, WIDE_SAFE)
            render_finish(accent, (640, 360), dict(LIGHT, accent="#FC00FC"), WIDE_STAGE, WIDE_SAFE)
            self.assertEqual(blue.read_bytes(), accent.read_bytes())
            blue_pixel = pixel(pixels(blue), 640, 600, 250)
            warm_pixel = pixel(pixels(warm), 640, 600, 250)
            self.assertGreater(difference(blue_pixel, warm_pixel), 20)
            self.assertGreater(blue_pixel[2], blue_pixel[0])
            self.assertGreater(warm_pixel[0], warm_pixel[2])

    def test_all_three_icon_colours_contribute_and_fallback_uses_accent(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            red, green = root / "red.png", root / "green.png"
            first = dict(LIGHT, gradient_colors=["#3456AA", "#EE3322", "#3456AA"])
            second = dict(first, gradient_colors=["#3456AA", "#22BB44", "#3456AA"])
            render_finish(red, (640, 360), first, WIDE_STAGE, WIDE_SAFE)
            render_finish(green, (640, 360), second, WIDE_STAGE, WIDE_SAFE)
            self.assertGreater(difference(pixel(pixels(red), 640, 600, 180),
                                          pixel(pixels(green), 640, 600, 180)), 15)
            fallback = {key: value for key, value in LIGHT.items() if key != "gradient_colors"}
            result = render_finish(root / "fallback.png", (640, 360), fallback, WIDE_STAGE, WIDE_SAFE)
            self.assertEqual(result["gradient_colors"], [LIGHT["accent"], LIGHT["accent"]])
            self.assertEqual(result["gradient_source"], "accent-fallback")

    def test_render_is_deterministic_opaque_srgb_and_reports_actual_samples(self):
        with TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first.png", Path(temporary) / "second.png"
            for output in (first, second):
                result = render_finish(output, (640, 360), LIGHT, WIDE_STAGE, WIDE_SAFE, motif="paths")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            description = subprocess.run(["magick", "identify", "-format", "%w|%h|%[opaque]|%[colorspace]", str(first)],
                                         check=True, capture_output=True, text=True).stdout
            self.assertEqual(description.lower(), "640|360|true|srgb")
            self.assertEqual(result["version"], FINISH_VERSION)
            data = pixels(first)
            for sample in result["gradient_samples"]:
                self.assertEqual(pixel(data, 640, sample["x"], sample["y"]), rgb(sample["color"]))

    def test_large_canvas_uses_bounded_working_layer_without_a_stage_edge(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "large.png"
            stage = {"x": 900, "y": 40, "width": 600, "height": 780}
            safe = {"x": 80, "y": 40, "width": 1400, "height": 780}
            result = render_finish(output, (1600, 900), DARK, stage, safe)
            self.assertEqual(result["atmosphere_working_size"], [768, 432])
            data = pixels(output)
            for x in range(stage["x"] - 3, stage["x"] + 3):
                self.assertLessEqual(difference(pixel(data, 1600, x, 450),
                                                pixel(data, 1600, x + 1, 450)), 1)

    def test_one_pixel_canvas_keeps_reported_samples_inside_output(self):
        with TemporaryDirectory() as temporary:
            box = {"x": 0, "y": 0, "width": 1, "height": 1}
            result = render_finish(Path(temporary) / "tiny.png", (1, 1), LIGHT, box, box)
            self.assertTrue(all(sample["x"] == 0 and sample["y"] == 0
                                for sample in result["gradient_samples"]))


if __name__ == "__main__":
    unittest.main()
