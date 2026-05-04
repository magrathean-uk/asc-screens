import unittest

from asc_screens import (
    background_command,
    classify_device_from_size,
    derive_background_palette,
    fit_inside,
    resolve_background_palette,
    target_for_kind,
)


class AscFrameMakerTests(unittest.TestCase):
    def test_target_for_kind(self):
        self.assertEqual(target_for_kind("iphone"), (1284, 2778))
        self.assertEqual(target_for_kind("ipad"), (2064, 2752))

    def test_fit_inside_preserves_aspect_ratio(self):
        self.assertEqual(fit_inside((1470, 3000), (1110, 2530)), (1110, 2265))
        self.assertEqual(fit_inside((2300, 3000), (1840, 2400)), (1840, 2400))

    def test_fit_inside_never_upscales(self):
        self.assertEqual(fit_inside((100, 200), (1000, 1000)), (100, 200))

    def test_classify_device_from_size(self):
        self.assertEqual(classify_device_from_size(1284, 2778), "iphone")
        self.assertEqual(classify_device_from_size(2064, 2752), "ipad")

    def test_teslatlas_background_is_imagemagick_command(self):
        command = background_command(1284, 2778, resolve_background_palette(theme="teslatlas"))
        self.assertEqual(command[:3], ["-size", "1284x2778", "xc:#060914"])
        self.assertIn("-sparse-color", command)

    def test_single_color_background_becomes_three_colors(self):
        palette = resolve_background_palette("#FF8800")
        self.assertEqual(len(palette), 3)
        self.assertTrue(all(color.startswith("#") and len(color) == 7 for color in palette))

    def test_background_derivation_changes_hue(self):
        palette = derive_background_palette("#FF8800")
        self.assertEqual(len(palette), 3)
        self.assertNotEqual(palette[0], palette[1])


if __name__ == "__main__":
    unittest.main()
