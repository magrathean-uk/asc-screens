import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from asc_icon_palette import extract_icon_palette


@unittest.skipUnless(shutil.which("magick"), "ImageMagick is not installed")
class IconPaletteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="icon-palette-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def image(self, name, *arguments):
        path = self.root / name
        subprocess.run(["magick", *arguments, str(path)], check=True, capture_output=True)
        return path

    def test_area_weighted_brand_colours_win_over_white_and_tiny_fleck(self):
        path = self.image("logo.png", "-size", "64x64", "xc:white", "-fill", "#2255CC",
                          "-draw", "rectangle 0,0 23,63", "-fill", "#22AA66", "-draw",
                          "rectangle 24,0 39,63", "-fill", "#FF00FF", "-draw", "point 63,63")
        result = extract_icon_palette(path)
        self.assertEqual(result["colors"][:2], ["#2255CC", "#22AA66"])
        self.assertEqual(result["accent"], "#2255CC")
        self.assertNotIn("#FF00FF", result["colors"])
        self.assertEqual(result["selection"], "chromatic")
        self.assertLessEqual(len(result["swatches"]), 12)

    def test_transparent_hidden_rgb_does_not_influence_palette(self):
        path = self.image("hidden.png", "-size", "64x64", "xc:#FF00FF", "-alpha", "set",
                          "-channel", "A", "-evaluate", "set", "0", "+channel", "-fill",
                          "#2255CC", "-draw", "rectangle 0,0 15,63")
        result = extract_icon_palette(path)
        self.assertEqual(result["colors"], ["#2255CC", "#2255CC"])
        self.assertEqual(result["visible_pixel_weight"], 1024)
        self.assertEqual([item["color"] for item in result["swatches"]], ["#2255CC"])

    def test_partial_alpha_counts_visible_area(self):
        path = self.image("alpha.png", "-size", "32x64", "xc:#2255CC", "(", "-size",
                          "32x64", "xc:rgba(34,170,102,0.25)", ")", "+append")
        result = extract_icon_palette(path)
        self.assertEqual(result["accent"], "#2255CC")
        weights = {item["color"]: item["weight"] for item in result["swatches"]}
        self.assertAlmostEqual(weights["#22AA66"], 2048 * 64 / 255, delta=.01)

    def test_greyscale_remains_neutral(self):
        path = self.image("grey.png", "-size", "64x64", "xc:#333333", "-fill", "#BBBBBB",
                          "-draw", "rectangle 32,0 63,63")
        result = extract_icon_palette(path)
        self.assertEqual(result["selection"], "neutral")
        self.assertEqual(set(result["colors"]), {"#333333", "#BBBBBB"})

    def test_charcoal_background_does_not_swallow_coloured_logo(self):
        path = self.image("charcoal.png", "-size", "64x64", "xc:#272E41", "-fill",
                          "#31CCDC", "-draw", "rectangle 0,0 7,63")
        self.assertEqual(extract_icon_palette(path)["accent"], "#31CCDC")

    def test_deterministic_json_safe_and_original_preserved(self):
        path = self.image("stable.png", "-size", "64x64", "gradient:#2255CC-#22AA66")
        before = path.read_bytes()
        first, second = extract_icon_palette(path), extract_icon_palette(path)
        self.assertEqual(first, second)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(first["source_sha256"], hashlib.sha256(before).hexdigest())
        json.dumps(first)
        self.assertTrue(set(first["colors"]).issubset(
            {swatch["color"] for swatch in first["swatches"]}))

    def test_changed_pixels_change_palette_and_hash(self):
        path = self.image("changing.png", "-size", "20x20", "xc:#2255CC")
        before = extract_icon_palette(path)
        self.image("changing.png", "-size", "20x20", "xc:#22AA66")
        after = extract_icon_palette(path)
        self.assertNotEqual(before["colors"], after["colors"])
        self.assertNotEqual(before["source_sha256"], after["source_sha256"])

    def test_missing_bad_and_empty_images_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "readable file"):
            extract_icon_palette(self.root / "missing.png")
        bad = self.root / "broken.png"
        bad.write_text("not an icon")
        with self.assertRaisesRegex(ValueError, "Cannot read app icon"):
            extract_icon_palette(bad)
        empty = self.image("empty.png", "-size", "20x20", "xc:none")
        with self.assertRaisesRegex(ValueError, "no visible pixels"):
            extract_icon_palette(empty)


if __name__ == "__main__":
    unittest.main()
