import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import asc_creative as creative


class CreativeAssetTests(unittest.TestCase):
    def test_design_frame_paths_expand_environment_variables(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "design.json"
            config.write_text(json.dumps({"app_name": "App", "title": "Useful work",
                                          "frame_assets": "$ASC_TEST_LIBRARY/frames",
                                          "frames_bin": "$ASC_TEST_TOOLS/frames"}))
            with patch.dict("os.environ", {"ASC_TEST_LIBRARY": str(root / "library"),
                                           "ASC_TEST_TOOLS": str(root / "tools")}):
                loaded = creative.load_creative_design(config)
            self.assertEqual(loaded["frame_assets"], str(root / "library" / "frames"))
            self.assertEqual(loaded["frames_bin"], str(root / "tools" / "frames"))

    def test_composed_design_is_rendered_and_manifest_records_final_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(b"original")
            output = root / "exports"

            def compose(source_path, staged_path, size, design):
                Path(staged_path).write_bytes(b"composed")
                return {"title": design["title"], "output": str(staged_path), "validated": True}

            with patch("asc_design.render_design", side_effect=compose) as render, \
                    patch.object(creative, "validate_creative_file", return_value=()):
                files = creative.process_creative_assets(source, output, "header",
                                                       design={"app_name": "Nodex", "title": "Your servers."})
            self.assertEqual(render.call_args.args[2], (3840, 1646))
            manifest = json.loads((output / "asc_upload.json").read_text())
            self.assertEqual(manifest["creative_assets"][0]["design"]["output"], str(files[0]))
            self.assertEqual(source.read_bytes(), b"original")

    def test_composed_video_is_rejected_before_rendering_or_output_creation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mov"
            source.touch()
            output = root / "exports"
            with patch.object(creative, "inspect_creative_video") as probe:
                with self.assertRaisesRegex(ValueError, "image sources"):
                    creative.process_creative_assets(source, output, "header", design={"app_name": "Nodex"})
            probe.assert_not_called()
            self.assertFalse(output.exists())

    def test_profiles_match_apple_dimensions_and_placements(self):
        self.assertEqual((creative.CREATIVE_PROFILES["header"].width,
                          creative.CREATIVE_PROFILES["header"].height), (3840, 1646))
        self.assertEqual((creative.CREATIVE_PROFILES["universal"].width,
                          creative.CREATIVE_PROFILES["universal"].height), (5244, 2950))
        self.assertFalse(creative.CREATIVE_PROFILES["universal"].video)
        self.assertEqual(creative.CREATIVE_PROFILES["universal"].placements,
                         ("PRODUCT_PAGE_HEADER_ASSET", "APP_STORE_SEARCH_RESULTS_ASSET"))

    def test_discovery_excludes_output_and_generated_directories(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("input.png", "nested/clip.mov", "asc_out/old.png", "_framed/old.png", "result/old.png"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual(creative.discover_creative_sources(root, root / "result"),
                             [root / "input.png", root / "nested/clip.mov"])

    def test_discovery_rejects_output_that_contains_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "input.png"
            path.touch()
            for source in (path, root):
                with self.assertRaisesRegex(ValueError, "must not contain"):
                    creative.discover_creative_sources(source, root)

    def test_same_stem_and_nested_names_have_distinct_output_names(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / name for name in ("one.png", "one.jpg", "nested/one.png")]
            names = [creative._output_stem(path, root) for path in paths]
            self.assertEqual(len(set(names)), 3)

    def test_contain_and_cover_preserve_aspect_ratio_and_strip_alpha(self):
        contain = creative.build_creative_image_command("input.png", "output.png", "header")
        cover = creative.build_creative_image_command("input.png", "output.png", "header", "cover")
        self.assertEqual(contain[contain.index("-resize") + 1], "3840x1646")
        self.assertEqual(cover[cover.index("-resize") + 1], "3840x1646^")
        self.assertIn("remove", contain)
        self.assertIn("off", contain)
        self.assertTrue(contain[-1].startswith("PNG24:"))

    def test_video_uses_silent_h264_without_screenshot_level_limit(self):
        command = creative.build_creative_video_command("input.mov", "output.mp4", "search-results", fps=60)
        filters = command[command.index("-vf") + 1]
        self.assertIn("force_original_aspect_ratio=decrease", filters)
        self.assertIn("pad=3840:2560", filters)
        self.assertIn("fps=60", filters)
        self.assertIn("libx264", command)
        self.assertIn("-an", command)
        self.assertNotIn("-level", command)
        self.assertNotIn("-level:v", command)
        cover = creative.build_creative_video_command("input.mov", "output.mp4", "event-detail", "cover")
        self.assertIn("crop=2160:3840", cover[cover.index("-vf") + 1])

    def test_validate_image_checks_alpha_even_if_opaque_and_exact_header_size(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.png"
            path.touch()
            info = {"format": "PNG", "width": 3840, "height": 1646, "alpha": False}
            with patch.object(creative, "inspect_creative_image", return_value=info):
                self.assertEqual(creative.validate_creative_file(path, "header"), ())
                info["alpha"] = True
                self.assertTrue(any("alpha" in problem for problem in creative.validate_creative_file(path, "header")))
                info["width"] = 3839
                self.assertTrue(any("size" in problem.lower() for problem in creative.validate_creative_file(path, "header")))

    def test_ratio_ranges_and_universal_png_requirement(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.jpg"
            path.touch()
            info = {"format": "JPEG", "width": 1920, "height": 1280, "alpha": False}
            with patch.object(creative, "inspect_creative_image", return_value=info):
                self.assertEqual(creative.validate_creative_file(path, "search-results"), ())
                info["height"] = 1281
                self.assertTrue(any("Aspect ratio" in problem for problem in
                                    creative.validate_creative_file(path, "search-results")))
                info.update(width=5244, height=2950)
                self.assertTrue(any("PNG" in problem for problem in creative.validate_creative_file(path, "universal")))

    def test_video_minimum_duration_frame_rate_and_universal_video(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.mov"
            path.touch()
            info = {"format": "mov,mp4,m4a,3gp,3g2,mj2", "width": 3840, "height": 2160,
                    "duration": 15, "fps": 30}
            with patch.object(creative, "inspect_creative_video", return_value=info):
                self.assertEqual(creative.validate_creative_file(path, "event-card"), ())
                info["duration"] = 14.9
                info["fps"] = 24
                problems = creative.validate_creative_file(path, "event-card")
                self.assertTrue(any("duration" in problem for problem in problems))
                self.assertTrue(any("frame rate" in problem for problem in problems))
                self.assertTrue(any("images only" in problem for problem in creative.validate_creative_file(path, "universal")))

    def test_check_rejects_png_content_with_jpeg_extension(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.jpg"
            path.touch()
            info = {"format": "PNG", "width": 3840, "height": 1646, "alpha": False}
            with patch.object(creative, "inspect_creative_image", return_value=info):
                self.assertTrue(any("filename extension" in problem for problem in
                                    creative.validate_creative_file(path, "header")))

    def test_image_identification_does_not_confuse_gray_with_alpha(self):
        result = type("Result", (), {"stdout": "PNG 3840 1646 gray"})()
        with patch.object(creative, "_run", return_value=result):
            self.assertFalse(creative.inspect_creative_image("input.png")["alpha"])
            result.stdout = "PNG 3840 1646 srgba 4.0"
            self.assertTrue(creative.inspect_creative_image("input.png")["alpha"])

    def test_ffprobe_uses_stream_duration_and_average_frame_rate(self):
        result = type("Result", (), {"stdout": json.dumps({
            "streams": [{"width": 3840, "height": 1646, "duration": "7.5",
                         "avg_frame_rate": "60/1", "r_frame_rate": "120/1"}],
            "format": {"duration": "9", "format_name": "mov,mp4"}})})()
        with patch.object(creative, "_run", return_value=result):
            info = creative.inspect_creative_video("input.mov")
        self.assertEqual(info["duration"], 7.5)
        self.assertEqual(info["fps"], 60)

    def test_generation_rejects_short_video_before_creating_outputs(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.mov"
            path.touch()
            output = Path(tmp) / "exports"
            with patch.object(creative, "inspect_creative_video", return_value={"duration": 4.9}), \
                    patch.object(creative, "_run") as run:
                with self.assertRaisesRegex(ValueError, "at least 5"):
                    creative.process_creative_assets(path, output, "header")
                run.assert_not_called()
            self.assertFalse(output.exists())

    def test_profile_directory_symlink_cannot_redirect_output_into_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            capture = source / "capture.png"
            capture.write_bytes(b"original")
            output = root / "exports"
            output.mkdir()
            (output / "header").symlink_to(source, target_is_directory=True)
            with patch.object(creative, "_run") as run:
                with self.assertRaisesRegex(ValueError, "overlap source"):
                    creative.process_creative_assets(source, output, "header")
                run.assert_not_called()
            self.assertEqual(capture.read_bytes(), b"original")

    def test_profile_symlink_cannot_alias_another_profile(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "capture.png"
            source.touch()
            output = root / "exports"
            (output / "search-results").mkdir(parents=True)
            (output / "header").symlink_to(output / "search-results", target_is_directory=True)
            with patch.object(creative, "_run") as run:
                with self.assertRaisesRegex(ValueError, "profile-directory symlink"):
                    creative.process_creative_assets(source, output, "creative-all")
                run.assert_not_called()

    def test_max_duration_and_poster_time_are_checked_before_rendering(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.mp4"
            path.touch()
            with patch.object(creative, "inspect_creative_video", return_value={"duration": 20}), \
                    patch.object(creative, "_run") as run:
                with self.assertRaisesRegex(ValueError, "at least 15"):
                    creative.process_creative_assets(path, Path(tmp) / "exports", "event-card", max_duration=10)
                with self.assertRaisesRegex(ValueError, "Poster time"):
                    creative.process_creative_assets(path, Path(tmp) / "exports", "header", poster_time=20)
                run.assert_not_called()

    def test_creative_all_generates_five_images_four_videos_and_manifest(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "capture.png").write_bytes(b"source image")
            (source / "capture.mov").write_bytes(b"source movie")
            output = Path(tmp) / "exports"

            def render(command):
                target = command[-1]
                if target.startswith("PNG24:"):
                    target = target[len("PNG24:"):]
                Path(target).write_bytes(b"generated media")

            with patch.object(creative, "_run", side_effect=render), \
                    patch.object(creative, "inspect_creative_video", return_value={"duration": 20}), \
                    patch.object(creative, "validate_creative_file", return_value=()):
                outputs = creative.process_creative_assets(source, output, "creative-all", locale="en-GB", poster_time=2)
            self.assertEqual(len(outputs), 9)
            self.assertTrue(all(path.exists() for path in outputs))
            manifest = json.loads((output / "asc_upload.json").read_text())
            self.assertEqual(manifest["locales"], {})
            self.assertEqual(len(manifest["creative_assets"]), 9)
            videos = [entry for entry in manifest["creative_assets"] if entry["media_type"] == "video"]
            self.assertEqual(len(videos), 4)
            self.assertTrue(all(Path(entry["poster_path"]).exists() for entry in videos))
            self.assertTrue(all(entry["poster_time"] == 2 for entry in videos))
            self.assertTrue(all(entry["profile"] != "universal" for entry in videos))
            self.assertTrue(all(entry["locale"] == "en-GB" for entry in manifest["creative_assets"]))
            self.assertEqual((source / "capture.png").read_bytes(), b"source image")
            review = (output / "asc_creative_review.html").read_text()
            self.assertIn("<video controls", review)
            self.assertNotIn(str(output), review)
            self.assertTrue((output / "asc_creative_review.json").exists())

    def test_review_percent_encodes_hash_and_query_characters_in_filename(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "header" / "capture#1?.png"
            creative._write_creative_reviews(root, [{"profile": "header", "path": str(path),
                "media_type": "image", "locale": "default", "width": 3840, "height": 1646}])
            review = (root / "asc_creative_review.html").read_text()
            self.assertIn('src="header/capture%231%3F.png"', review)

    def test_failed_export_does_not_replace_prior_manifest(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "capture.png"
            source.write_bytes(b"source")
            output = Path(tmp) / "exports"
            output.mkdir()
            (output / "asc_upload.json").write_text("previous set")
            with patch.object(creative, "_run", side_effect=RuntimeError("render failed")):
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    creative.process_creative_assets(source, output, "header")
            self.assertEqual((output / "asc_upload.json").read_text(), "previous set")
            self.assertEqual(list(output.iterdir()), [output / "asc_upload.json"])

    def test_validation_failures_are_fatal_to_generation(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "capture.png"
            source.touch()
            output = Path(tmp) / "exports"
            with patch.object(creative, "_run"), \
                    patch.object(creative, "validate_creative_file", return_value=("wrong size",)):
                with self.assertRaisesRegex(RuntimeError, "wrong size"):
                    creative.process_creative_assets(source, output, "header")
            self.assertFalse((output / "asc_upload.json").exists())

    def test_check_all_matches_any_profile_and_propagates_failures(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.png"
            path.touch()
            with contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(creative, "validate_creative_file", side_effect=lambda path, name: () if name == "universal" else ("wrong size",)):
                self.assertEqual(creative.check_creative_assets(path, "creative-all"), 0)
            with contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(creative, "validate_creative_file", return_value=("wrong size",)):
                self.assertEqual(creative.check_creative_assets(path, "header"), 1)

    def test_check_accepts_explicit_asc_out_directory(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "asc_out" / "universal"
            output.mkdir(parents=True)
            (output / "capture.png").touch()
            with contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(creative, "validate_creative_file", return_value=()) as validate:
                self.assertEqual(creative.check_creative_assets(output, "universal"), 0)
            validate.assert_called_once_with(output / "capture.png", "universal")


if __name__ == "__main__":
    unittest.main()
