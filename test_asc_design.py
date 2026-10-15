"""Geometry and input-safety checks for local editorial asset composition."""

import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import asc_design as design


def measure(text, width, pointsize, weight):
    # Font-independent test measurement; rendering separately measures the
    # selected font with ImageMagick before positioning any text.
    capacity = max(1, int(width / (pointsize * .55)))
    lines = sum(max(1, math.ceil(len(line) / capacity)) for line in text.split("\n"))
    return math.ceil(pointsize * 1.2) * lines


def intersects(first, second):
    return (first["x"] < second["x"] + second["width"] and
            first["x"] + first["width"] > second["x"] and
            first["y"] < second["y"] + second["height"] and
            first["y"] + first["height"] > second["y"])


def inside(inner, outer):
    return (inner["x"] >= outer["x"] - 1 and inner["y"] >= outer["y"] - 1 and
            inner["x"] + inner["width"] <= outer["x"] + outer["width"] + 1 and
            inner["y"] + inner["height"] <= outer["y"] + outer["height"] + 1)


class ComposedDesignTests(unittest.TestCase):
    profiles = ((3840, 1646), (3840, 2560), (5244, 2950), (3840, 2160), (2160, 3840))
    copy = {"app_name": "Nodex", "title": "Your servers.\nIn your hands.",
            "subtitle": "Keep your infrastructure close.", "detail": "SSH · containers · alerts"}

    def test_every_profile_keeps_text_and_whole_device_inside_safe_area(self):
        for size in self.profiles:
            for source in ((1320, 2868), (2064, 2752), (1920, 1080)):
                for layout in ("hero", "spotlight"):
                    with self.subTest(size=size, source=source, layout=layout):
                        result = design.plan_design(size, source, dict(self.copy, layout=layout), measure)
                        boxes = list(result["text_boxes"].values())
                        for box in boxes + [result["device_box"]]:
                            self.assertTrue(inside(box, result["safe_area"]), box)
                        for index, box in enumerate(boxes):
                            self.assertFalse(intersects(box, result["device_box"]))
                            for following in boxes[index + 1:]:
                                self.assertFalse(intersects(box, following))
                        self.assertIsNone(result["accent_rule_box"])
                        self.assertEqual(result["motif"], "none")
                        media = result["media_box"]
                        self.assertAlmostEqual(media["width"] / media["height"], source[0] / source[1], delta=.004)
                        self.assertGreater(media["height"], size[1] * .24)

    def test_long_headline_shrinks_but_remains_readable_and_fails_when_excessive(self):
        short = design.plan_design((3840, 1646), (1320, 2868), self.copy, measure)
        long = design.plan_design((3840, 1646), (1320, 2868), dict(self.copy,
            title="Infrastructure, wherever you need it"), measure)
        self.assertLess(long["text_boxes"]["title"]["pointsize"], short["text_boxes"]["title"]["pointsize"])
        self.assertGreater(long["text_boxes"]["title"]["pointsize"], 120)
        with self.assertRaisesRegex(ValueError, "too long"):
            design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, title="Long headline " * 100), measure)

    @unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
    def test_explicit_two_line_heading_stays_two_lines_with_actual_font(self):
        result = design.plan_design((3840, 1646), (960, 1100),
            dict(self.copy, title="Move files.\nKeep working.", media_kind="image"))
        title = result["text_boxes"]["title"]
        line_height = design._measure("Ag", title["width"], title["pointsize"], "bold")
        self.assertLessEqual(title["height"], line_height * 2 + 1)
        self.assertGreater(title["pointsize"], 160)

    def test_icon_and_identity_do_not_overlap(self):
        result = design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, icon="icon.png"), measure)
        self.assertFalse(intersects(result["icon_box"], result["text_boxes"]["app_name"]))
        self.assertTrue(inside(result["icon_box"], result["safe_area"]))

    def test_universal_composition_is_inside_both_central_crop_ratios(self):
        result = design.plan_design((5244, 2950), (2064, 2752), self.copy, measure)
        # Conservative guide fits header's 3840:1646 crop and search's 3:2 crop.
        header_height = 5244 * 1646 / 3840
        header = design._box(0, (2950 - header_height) / 2, 5244, header_height)
        search = design._box((5244 - 2950 * 1.5) / 2, 0, 2950 * 1.5, 2950)
        self.assertTrue(inside(result["safe_area"], header))
        self.assertTrue(inside(result["safe_area"], search))

    def test_palette_and_source_modes_are_explicit(self):
        for source, expected in (((1320, 2868), "iphone"), ((2064, 2752), "ipad"), ((1920, 1080), "image")):
            result = design.plan_design((3840, 1646), source, dict(self.copy, style="dark", accent="#11CC99"), measure)
            self.assertEqual(result["media_kind"], expected)
            self.assertEqual(result["palette"]["accent"], "#11CC99")
        framed = design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, media_kind="framed"), measure)
        self.assertEqual(framed["device_box"], framed["media_box"])
        for field, value in (("style", "unknown"), ("layout", "cover"), ("media_kind", "video"),
                             ("accent", "red; command"), ("title", "")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, **{field: value}), measure)

    def test_flat_finish_preserves_existing_content_geometry_without_decorations(self):
        studio = design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, motif="grid"), measure)
        flat = design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, finish="flat"), measure)
        self.assertIsNone(flat["accent_rule_box"])
        self.assertIsNone(studio["accent_rule_box"])
        self.assertEqual(studio["text_boxes"], flat["text_boxes"])
        self.assertEqual(studio["media_box"], flat["media_box"])
        for field, value in (("finish", "neon"), ("motif", "chart")):
            with self.assertRaises(ValueError):
                design.plan_design((3840, 1646), (1320, 2868), dict(self.copy, **{field: value}), measure)

    def test_render_rejects_source_overwrite_and_missing_icon_before_rendering(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source.png"
            source.write_bytes(b"source")
            with patch.object(design, "_run") as run:
                with self.assertRaisesRegex(ValueError, "overwrite"):
                    design.render_design(source, source, (3840, 1646), self.copy)
                with self.assertRaisesRegex(ValueError, "icon does not exist"):
                    design.render_design(source, Path(temp) / "result.png", (3840, 1646),
                                         dict(self.copy, icon=str(Path(temp) / "missing.png")))
                run.assert_not_called()
            self.assertEqual(source.read_bytes(), b"source")

    def test_copy_percent_properties_are_rendered_as_literal_text(self):
        self.assertEqual(design._literal("100% %[filename]"), "100%% %%[filename]")
        self.assertEqual(design._literal("@copy"), "\\@copy")

    @unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
    def test_icon_colors_override_manual_accent_and_follow_icon_changes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source, icon = root / "source.png", root / "icon.png"
            subprocess.run(["magick", "-size", "640x400", "xc:white", str(source)], check=True)
            results = []
            for name, color in (("red", "#D02040"), ("blue", "#2040D0")):
                subprocess.run(["magick", "-size", "64x64", f"xc:{color}", str(icon)], check=True)
                original = icon.read_bytes()
                plan = design.render_design(source, root / f"{name}.png", (960, 540),
                    {"app_name": "App", "title": "Useful work.", "media_kind": "image",
                     "icon": str(icon), "accent": "#00FF00", "motif": "orbits"})
                self.assertEqual(icon.read_bytes(), original)
                self.assertEqual(plan["palette"]["gradient_colors"], [color, color])
                self.assertEqual(plan["finish_background"]["gradient_colors"], [color, color])
                self.assertEqual(plan["finish_background"]["gradient_source"], "icon")
                self.assertFalse(plan["finish_background"]["stage_drawn"])
                self.assertEqual(plan["finish_background"]["motif_paths"], 0)
                self.assertIsNone(plan["accent_rule_box"])
                results.append(plan)
            self.assertNotEqual(results[0]["icon_palette"]["source_sha256"],
                                results[1]["icon_palette"]["source_sha256"])
            self.assertNotEqual(results[0]["finish_background"]["gradient_samples"],
                                results[1]["finish_background"]["gradient_samples"])

    @unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
    def test_complete_native_device_is_fitted_without_clipping_its_buttons(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for kind, source_size, frame_size in (
                ("iphone", (132, 287), (520, 1000)),
                ("ipad", (206, 275), (760, 1000)),
            ):
                source, frame = root / f"{kind}.png", root / f"{kind}-frame.png"
                subprocess.run(["magick", "-size", f"{source_size[0]}x{source_size[1]}",
                                "xc:white", str(source)], check=True)
                subprocess.run(["magick", "-size", f"{frame_size[0]}x{frame_size[1]}", "xc:none",
                                "-fill", "green", "-draw", f"rectangle 30,20 {frame_size[0]-30},980",
                                "-fill", "red", "-draw", "rectangle 0,200 30,260", str(frame)], check=True)
                output = root / f"{kind}-creative.png"
                metadata = {"provider": "Apple Frames", "device": kind, "framed_size": list(frame_size)}
                with patch.object(design, "render_device_frame", return_value=(frame, metadata)) as native:
                    plan = design.render_design(source, output, (1600, 900),
                        {"app_name": "App", "title": "Useful work.", "media_kind": kind})
                native.assert_called_once()
                self.assertEqual(plan["source_size"], list(source_size))
                self.assertEqual(plan["framed_size"], list(frame_size))
                self.assertEqual(plan["device_frame"], metadata)
                self.assertTrue(inside(plan["device_box"], plan["safe_area"]))
                box = plan["media_box"]
                scale = min(box["width"] / frame_size[0], box["height"] / frame_size[1])
                x, y = box["x"] + round(12 * scale), box["y"] + round(230 * scale)
                pixel = subprocess.run(["magick", str(output), "-crop", f"1x1+{x}+{y}",
                                        "-format", "%[hex:p{0,0}]", "info:"],
                                       check=True, text=True, capture_output=True).stdout.strip()
                self.assertEqual(pixel[:6].upper(), "FF0000", "The physical button was clipped or repainted")

    def test_device_frame_failure_never_falls_back_to_a_drawn_bezel(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "source.png", root / "output.png"
            source.write_bytes(b"source")
            output.write_bytes(b"previous successful render")
            with patch.object(design, "_inspect", return_value=(1320, 2868)), \
                    patch.object(design, "render_device_frame", side_effect=RuntimeError("Frames assets missing")):
                with self.assertRaisesRegex(RuntimeError, "Frames assets missing"):
                    design.render_design(source, output, (1600, 900), self.copy)
            self.assertEqual(output.read_bytes(), b"previous successful render")

    @unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
    def test_feature_images_and_already_framed_sources_do_not_add_devices(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            subprocess.run(["magick", "-size", "640x400", "xc:white", str(source)], check=True)
            with patch.object(design, "render_device_frame") as native:
                for kind in ("image", "framed"):
                    result = design.render_design(source, root / f"{kind}.png", (1600, 900),
                        {"app_name": "App", "title": "Useful work.", "media_kind": kind})
                    self.assertNotIn("device_frame", result)
            native.assert_not_called()

    @unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
    def test_icon_corner_finish_preserves_original_transparent_details(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source, icon, mask = root / "source.png", root / "icon.png", root / "mask.png"
            subprocess.run(["magick", "-size", "640x400", "xc:white", str(source)], check=True)
            subprocess.run(["magick", "-size", "100x100", "xc:white", "-fill", "black",
                            "-draw", "circle 50,50 70,50", str(mask)], check=True)
            subprocess.run(["magick", "-size", "100x100", "xc:red", str(mask), "-alpha", "off",
                            "-compose", "CopyOpacity", "-composite", str(icon)], check=True)
            output = root / "creative.png"
            plan = design.render_design(source, output, (1600, 900),
                {"app_name": "App", "title": "Useful work.", "media_kind": "image", "icon": str(icon)})
            box = plan["icon_box"]
            pixel = subprocess.run(["magick", str(output), "-crop",
                f"1x1+{box['x'] + box['width']//2}+{box['y'] + box['height']//2}",
                "-format", "%[hex:p{0,0}]", "info:"], check=True, text=True, capture_output=True).stdout.strip()
            actual = [int(pixel[index:index+2], 16) for index in (0, 2, 4)]
            background_path = root / "background.png"
            design.render_finish(background_path, (1600, 900), plan["palette"],
                                 plan["stage_box"], plan["safe_area"])
            background = subprocess.run(["magick", str(background_path), "-crop",
                f"1x1+{box['x'] + box['width']//2}+{box['y'] + box['height']//2}",
                "-format", "%[hex:p{0,0}]", "info:"], check=True, text=True, capture_output=True).stdout.strip()
            expected = [int(background[index:index+2], 16) for index in (0, 2, 4)]
            self.assertTrue(all(abs(a-b) <= 4 for a,b in zip(actual, expected)), pixel)


if __name__ == "__main__":
    unittest.main()
