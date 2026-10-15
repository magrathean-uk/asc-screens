import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import asc_gen
import asc_screens


class AssetCliTests(unittest.TestCase):
    def test_creative_dispatch_does_not_require_frames(self):
        with patch("sys.argv", ["asc-screens", "art.png", "--asset", "header", "--locale", "en-GB", "--background", "#123456"]), \
                patch("asc_screens.process_creative_assets", return_value=[Path("asc_out/header/art.png")]) as build, \
                patch("asc_screens.require_frames_bin") as frames:
            asc_screens.main()
        self.assertEqual(build.call_args.args[:3], ("art.png", "asc_out", "header"))
        self.assertEqual(build.call_args.kwargs["locale"], "en-GB")
        self.assertEqual(build.call_args.kwargs["background"], "#123456")
        frames.assert_not_called()

    def test_creative_check_propagates_validation_failure(self):
        with patch("sys.argv", ["asc-screens", "exports", "--asset", "search-results", "--check"]), \
                patch("asc_screens.check_creative_assets", return_value=1) as check, \
                patch("asc_screens.process_creative_assets") as build:
            with self.assertRaises(SystemExit) as error:
                asc_screens.main()
        self.assertEqual(error.exception.code, 1)
        check.assert_called_once_with("exports", "search-results")
        build.assert_not_called()

    def test_creative_config_resolves_input_file_and_output_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "assets.json"
            config.write_text(json.dumps({"source": "art.mov", "output_root": "export", "asset": "header",
                                          "asset_fit": "cover", "asset_fps": 60, "asset_max_duration": 8,
                                          "asset_poster_time": 2}), encoding="utf-8")
            with patch("sys.argv", ["asc-screens", "--config", str(config)]), \
                    patch("asc_screens.process_creative_assets", return_value=[]) as build:
                asc_screens.main()
            self.assertEqual(build.call_args.args, (root / "art.mov", root / "export", "header"))
            self.assertEqual(build.call_args.kwargs["fps"], 60)
            self.assertEqual(build.call_args.kwargs["fit"], "cover")
            self.assertEqual(build.call_args.kwargs["poster_time"], 2)

    def test_creative_render_failure_exits_with_diagnostic(self):
        with patch("sys.argv", ["asc-screens", "art.png", "--asset", "header"]), \
                patch("asc_screens.process_creative_assets", side_effect=ValueError("source too short")):
            with self.assertRaisesRegex(SystemExit, "source too short"):
                asc_screens.main()

    def test_design_file_resolves_icon_relative_to_its_own_directory(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            recipes = root / "designs"
            recipes.mkdir()
            design = recipes / "nodex.json"
            design.write_text(json.dumps({"app_name": "Nodex", "title": "Your servers. In sight.",
                                          "icon": "nodex.png", "style": "light"}))
            config = root / "assets.json"
            config.write_text(json.dumps({"source": "capture.png", "asset": "header",
                                          "design_file": "designs/nodex.json"}))
            with patch("sys.argv", ["asc-screens", "--config", str(config)]), \
                    patch("asc_screens.process_creative_assets", return_value=[]) as build:
                asc_screens.main()
            self.assertEqual(build.call_args.kwargs["design"]["app_name"], "Nodex")
            self.assertEqual(build.call_args.kwargs["design"]["icon"], str(recipes / "nodex.png"))

    def test_design_cannot_silently_apply_to_screenshot_mode(self):
        with patch("sys.argv", ["asc-screens", "shots", "--design-file", "nodex.json"]):
            with self.assertRaises(SystemExit) as error:
                asc_screens.main()
        self.assertEqual(error.exception.code, 2)

    def test_creative_device_design_honors_explicit_frames_flags(self):
        with TemporaryDirectory() as temp:
            recipe = Path(temp) / "design.json"
            recipe.write_text(json.dumps({"app_name": "App", "title": "Useful work."}))
            with patch("sys.argv", ["asc-screens", "shot.png", "--asset", "header", "--design-file", str(recipe),
                                    "--frames-bin", "/custom/frames", "--frame-color", "Deep Blue"]), \
                    patch("asc_screens.process_creative_assets", return_value=[]) as build:
                asc_screens.main()
            self.assertEqual(build.call_args.kwargs["design"]["frames_bin"], "/custom/frames")
            self.assertEqual(build.call_args.kwargs["design"]["frame_color"], "Deep Blue")

    def test_explicit_default_frame_color_still_overrides_recipe_color(self):
        with TemporaryDirectory() as temp:
            recipe = Path(temp) / "design.json"
            recipe.write_text(json.dumps({"app_name": "App", "title": "Useful work.", "frame_color": "Deep Blue"}))
            with patch("sys.argv", ["asc-screens", "shot.png", "--asset", "header", "--design-file", str(recipe),
                                    "--frame-color=Silver"]), \
                    patch("asc_screens.process_creative_assets", return_value=[]) as build:
                asc_screens.main()
            self.assertEqual(build.call_args.kwargs["design"]["frame_color"], "Silver")

    def test_guided_creative_accepts_file_and_routes_check(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "art.png"
            source.touch()
            with patch("asc_gen.ask", side_effect=[str(source), "check", "universal"]), \
                    patch("asc_gen.check_creative_assets", return_value=0) as check, \
                    patch("asc_gen.collect_jobs") as jobs:
                with self.assertRaises(SystemExit) as error:
                    asc_gen.main()
            self.assertEqual(error.exception.code, 0)
            check.assert_called_once_with(source, "universal")
            jobs.assert_not_called()

    def test_guided_screenshots_still_use_all_device_families(self):
        self.assertEqual(asc_gen.choose_asset(""), "screenshots")
        self.assertEqual(asc_gen.choose_kinds("all", []), ["iphone", "ipad", "mac"])
        self.assertEqual(asc_gen.choose_asset("event-detail"), "event-detail")

    def test_guided_video_preserves_requested_encoding_and_poster_options(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "art.mov"
            source.touch()
            answers = ["cover", "#123456", "en-GB", str(root / "export"), "60", "10", "2"]
            with patch("asc_gen.ask", side_effect=answers), \
                    patch("asc_gen.process_creative_assets", return_value=[]) as build:
                asc_gen.run_creative_guided(source, "build", "header")
            self.assertEqual(build.call_args.kwargs["fps"], 60)
            self.assertEqual(build.call_args.kwargs["max_duration"], 10)
            self.assertEqual(build.call_args.kwargs["poster_time"], 2)

    def test_guided_design_uses_recipe_without_resize_controls(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "screen.png"
            source.touch()
            recipe = root / "design.json"
            recipe.write_text(json.dumps({"app_name": "Nodex", "title": "Your servers."}))
            with patch("asc_gen.ask", side_effect=[str(recipe), "en-GB", str(root / "output")]) as ask, \
                    patch("asc_gen.process_creative_assets", return_value=[]) as build:
                asc_gen.run_creative_guided(source, "build", "header")
            self.assertEqual(ask.call_count, 3)
            self.assertEqual(build.call_args.kwargs["design"]["title"], "Your servers.")


if __name__ == "__main__":
    unittest.main()
