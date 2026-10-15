import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asc_screens_ci import (
    compute_design_fingerprint,
    load_ci_config,
    run_ci,
    upload_screenshots,
)


class AscScreensCiTests(unittest.TestCase):
    def test_shared_renderer_update_invalidates_existing_completion_key(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ".asc-screens-ci.json"
            path.write_text(json.dumps({"app_id": "123", "version": "1.2.3"}))
            with patch("asc_screens_ci.renderer_fingerprint", return_value="template-before"):
                before = load_ci_config(path)
            with patch("asc_screens_ci.renderer_fingerprint", return_value="template-after"):
                after = load_ci_config(path)
            self.assertNotEqual(before.cache_key, after.cache_key)

    def test_fingerprint_changes_for_design_inputs_not_unrelated_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shots").mkdir()
            (root / "shots" / "one.png").write_text("before", encoding="utf-8")
            (root / "copy.json").write_text('{"en-GB":{"title":"Before"}}', encoding="utf-8")
            (root / "notes.txt").write_text("unrelated", encoding="utf-8")

            first = compute_design_fingerprint(root, ["shots", "copy.json"])
            (root / "notes.txt").write_text("changed", encoding="utf-8")
            second = compute_design_fingerprint(root, ["shots", "copy.json"])
            (root / "copy.json").write_text('{"en-GB":{"title":"After"}}', encoding="utf-8")
            third = compute_design_fingerprint(root, ["shots", "copy.json"])

        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_load_ci_config_adds_default_design_inputs_and_device_types(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            asc_config = root / "asc-screens.json"
            asc_config.write_text(json.dumps({"source": "shots", "copy_file": "copy.json", "output_root": "out"}), encoding="utf-8")
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3", "asc_screens_config": "asc-screens.json"}), encoding="utf-8")

            config = load_ci_config(ci_config)

        self.assertEqual(config.design_inputs, tuple(str((Path(tmp) / value).resolve()) for value in ("asc-screens.json", "shots", "copy.json")))
        self.assertEqual(config.output_root, (Path(tmp) / "out").resolve())
        self.assertEqual(config.device_type_map["iphone"], "IPHONE_69")
        self.assertEqual(config.device_type_map["ipad"], "IPAD_PRO_3GEN_129")

    def test_upload_screenshots_runs_asc_commands_from_manifest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            (out / "en-GB" / "iphone").mkdir(parents=True)
            (out / "en-GB" / "iphone" / "01.png").touch()
            (out / "asc_upload.json").write_text(
                json.dumps(
                    {
                        "locales": {
                            "en-GB": {
                                "iphone": [
                                    {"slot": 1, "filename": "01.png", "path": str(out / "en-GB" / "iphone" / "01.png")}
                                ]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3", "output_root": "out"}), encoding="utf-8")
            config = load_ci_config(ci_config)
            calls = []

            def fake_runner(cmd, **kwargs):
                calls.append(cmd)
                if cmd[:3] == ["asc", "versions", "list"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": [{"id": "v1", "attributes": {"versionString": "1.2.3"}}]}), stderr="")
                if cmd[:3] == ["asc", "localizations", "list"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": [{"id": "loc1", "attributes": {"locale": "en-GB"}}]}), stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            upload_screenshots(config, runner=fake_runner)

        self.assertIn(["asc", "auth", "status", "--validate"], calls)
        self.assertIn(["asc", "versions", "list", "--app", "123", "--platform", "IOS", "--version", "1.2.3", "--paginate", "--output", "json"], calls)
        self.assertIn(
            [
                "asc",
                "screenshots",
                "upload",
                "--version-localization",
                "loc1",
                "--path",
                str((out / "en-GB" / "iphone").resolve()),
                "--device-type",
                "IPHONE_69",
                "--replace",
                "--confirm",
            ],
            calls,
        )

    def test_upload_screenshots_uses_default_locale_for_non_localized_output(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            (out / "iphone").mkdir(parents=True)
            (out / "iphone" / "01.png").touch()
            (out / "asc_upload.json").write_text(
                json.dumps({"locales": {"default": {"iphone": [{"slot": 1, "filename": "01.png", "path": str(out / "iphone" / "01.png")}]}}}),
                encoding="utf-8",
            )
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3", "output_root": "out", "default_locale": "en-GB"}), encoding="utf-8")
            config = load_ci_config(ci_config)
            calls = []

            def fake_runner(cmd, **kwargs):
                calls.append(cmd)
                if cmd[:3] == ["asc", "versions", "list"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": [{"id": "v1", "attributes": {"versionString": "1.2.3"}}]}), stderr="")
                if cmd[:3] == ["asc", "localizations", "list"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": [{"id": "loc1", "attributes": {"locale": "en-GB"}}]}), stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            upload_screenshots(config, runner=fake_runner)

        self.assertIn(["asc", "localizations", "list", "--version", "v1", "--output", "json", "--locale", "en-GB", "--paginate"], calls)

    def test_run_ci_cache_hit_skips_build_and_upload(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "asc-screens.json").write_text(json.dumps({"source": "shots", "output_root": "out"}), encoding="utf-8")
            (root / "shots").mkdir()
            (root / "shots" / "one.png").write_text("same", encoding="utf-8")
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3", "asc_screens_config": "asc-screens.json"}), encoding="utf-8")
            config = load_ci_config(ci_config)
            cache_dir = root / ".asc-screens-cache"
            cache_dir.mkdir()
            (cache_dir / f"{config.cache_key}.done").touch()
            calls = []

            result = run_ci(config, cache_dir=cache_dir, runner=lambda cmd, **kwargs: calls.append(cmd))

        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, [])

    def test_run_ci_cache_miss_builds_uploads_and_marks_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            (root / "asc-screens.json").write_text(json.dumps({"source": "shots", "output_root": "out"}), encoding="utf-8")
            (root / "shots").mkdir()
            (root / "shots" / "one.png").write_text("new", encoding="utf-8")
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3", "asc_screens_config": "asc-screens.json"}), encoding="utf-8")
            config = load_ci_config(ci_config)
            calls = []

            def fake_runner(cmd, **kwargs):
                calls.append(cmd)
                if cmd[:1] == ["asc-screens"]:
                    (out / "en-GB" / "iphone").mkdir(parents=True)
                    (out / "en-GB" / "iphone" / "01.png").touch()
                    (out / "asc_upload.json").write_text(
                        json.dumps({"locales": {"en-GB": {"iphone": [{"slot": 1, "filename": "01.png", "path": str(out / "en-GB" / "iphone" / "01.png")}]}}}),
                        encoding="utf-8",
                    )
                if cmd[:3] == ["asc", "versions", "list"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": [{"id": "v1", "attributes": {"versionString": "1.2.3"}}]}), stderr="")
                if cmd[:3] == ["asc", "localizations", "list"]:
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"data": [{"id": "loc1", "attributes": {"locale": "en-GB"}}]}), stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            result = run_ci(config, cache_dir=root / ".asc-screens-cache", runner=fake_runner)

            self.assertEqual(result.status, "uploaded")
            self.assertIn(["asc-screens", "--config", str((root / "asc-screens.json").resolve())], calls)
            self.assertTrue((root / ".asc-screens-cache" / f"{config.cache_key}.done").exists())

    def creative_fixture(self, root, target=None, media_type="image"):
        out = root / "out"
        out.mkdir()
        asset = out / ("header.mp4" if media_type == "video" else "header.png")
        asset.touch()
        manifest = {"locales": {}, "creative_assets": [{"profile": "header", "media_type": media_type, "path": str(asset), "locale": "default", "placements": ["PRODUCT_PAGE_HEADER_ASSET"]}]}
        (out / "asc_upload.json").write_text(json.dumps(manifest), encoding="utf-8")
        payload = {"app_id": "123", "version": "1.2.3", "output_root": "out", "default_locale": "en-GB"}
        if target:
            payload["creative_asset_target"] = target
        config_path = root / ".asc-screens-ci.json"
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        return load_ci_config(config_path), manifest

    def fake_asc_runner(self, calls):
        def run(cmd, **kwargs):
            calls.append(cmd)
            payload = {}
            if cmd[1:3] == ["versions", "list"]:
                payload = {"data": [{"id": "v1", "attributes": {"versionString": "1.2.3"}}]}
            elif cmd[1:3] == ["localizations", "list"]:
                payload = {"data": [{"id": "loc1", "attributes": {"locale": "en-GB"}}]}
            elif cmd[1:3] == ["asset-library", "view"]:
                payload = {"data": {"id": "library1"}}
            elif cmd[1:4] == ["asset-library", "images", "upload"]:
                payload = {"imageId": "image1", "uploaded": True, "ready": True}
            elif cmd[1:4] == ["asset-library", "videos", "upload"]:
                payload = {"videoId": "video1", "uploaded": True, "ready": True}
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return run

    def test_creative_only_upload_is_library_only_without_implicit_placement(self):
        with TemporaryDirectory() as tmp:
            config, _ = self.creative_fixture(Path(tmp))
            calls = []
            upload_screenshots(config, runner=self.fake_asc_runner(calls))
        self.assertTrue(any(cmd[1:4] == ["asset-library", "images", "upload"] for cmd in calls))
        self.assertFalse(any("placements" in cmd or "versions" in cmd or "screenshots" in cmd for cmd in calls))

    def test_video_creative_placement_uses_real_receipt_key_and_explicit_target(self):
        with TemporaryDirectory() as tmp:
            config, _ = self.creative_fixture(Path(tmp), {"kind": "version"}, media_type="video")
            calls = []
            upload_screenshots(config, runner=self.fake_asc_runner(calls))
        self.assertIn(["asc", "localizations", "placements", "create", "--localization-id", "loc1", "--video-id", "video1", "--placement-type", "PRODUCT_PAGE_HEADER_ASSET", "--placement-group", "DEFAULT_PROFILE", "--output", "json"], calls)

    def test_video_poster_time_sets_frame_before_placement_and_is_in_local_plan(self):
        with TemporaryDirectory() as tmp:
            config, manifest = self.creative_fixture(Path(tmp), {"kind": "version"}, media_type="video")
            manifest["creative_assets"][0].update({"poster_time": 1.234, "duration": 5.0})
            (config.output_root / "asc_upload.json").write_text(json.dumps(manifest))
            calls = []
            upload_screenshots(config, runner=self.fake_asc_runner(calls))
            setter = next(cmd for cmd in calls if "set-poster-frame" in cmd)
            self.assertEqual(setter[setter.index("--time-code") + 1], "00:00:01.234")
            self.assertLess(calls.index(setter), next(i for i, cmd in enumerate(calls) if "placements" in cmd))
            plan = run_ci(config, runner=self.fake_asc_runner([]), dry_run=True)
            self.assertTrue(any("set-poster-frame" in cmd for cmd in plan["commands"]))

    def test_invalid_poster_time_stops_before_authenticated_commands(self):
        for value in (-1, 5, float("nan"), float("inf")):
            with self.subTest(value=value), TemporaryDirectory() as tmp:
                config, manifest = self.creative_fixture(Path(tmp), media_type="video")
                manifest["creative_assets"][0].update({"poster_time": value, "duration": 5.0})
                (config.output_root / "asc_upload.json").write_text(json.dumps(manifest))
                calls = []
                with self.assertRaisesRegex(SystemExit, "poster_time"):
                    upload_screenshots(config, runner=self.fake_asc_runner(calls))
                self.assertEqual(calls, [])

    def test_custom_and_experiment_targets_use_their_explicit_localization_ids(self):
        for kind, prefix in (("custom-page", ["product-pages", "custom-pages"]), ("experiment-treatment", ["product-pages", "experiments", "treatments"])):
            with self.subTest(kind=kind), TemporaryDirectory() as tmp:
                config, _ = self.creative_fixture(Path(tmp), {"kind": kind, "localization_ids": {"en-GB": "target1"}})
                calls = []
                upload_screenshots(config, runner=self.fake_asc_runner(calls))
                placement = next(cmd for cmd in calls if "placements" in cmd)
                self.assertEqual(placement[1:1 + len(prefix)], prefix)
                self.assertEqual(placement[placement.index("--localization-id") + 1], "target1")
                self.assertFalse(any("versions" in cmd for cmd in calls))

    def test_dry_run_executes_no_build_auth_or_upload_commands(self):
        with TemporaryDirectory() as tmp:
            config, _ = self.creative_fixture(Path(tmp), {"kind": "version"})
            calls = []
            plan = run_ci(config, runner=self.fake_asc_runner(calls), dry_run=True)
            self.assertEqual(calls, [])
            self.assertEqual(len(plan["commands"]), 2)
            self.assertIn("<uploaded-asset:1>", plan["commands"][1])
            self.assertFalse((Path(tmp) / ".asc-screens-cache").exists())

    def test_every_family_is_preflighted_before_any_network_or_replacement(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, manifest = self.creative_fixture(root)
            path = config.output_root / "iphone"
            path.mkdir()
            (path / "01.png").touch()
            manifest["locales"] = {"default": {"iphone": [{"filename": "01.png", "path": str(path / "01.png")}], "mac": [{"filename": "01.png"}]}}
            (config.output_root / "asc_upload.json").write_text(json.dumps(manifest))
            calls = []
            with self.assertRaisesRegex(SystemExit, "device_type_map.*mac"):
                upload_screenshots(config, runner=self.fake_asc_runner(calls))
            self.assertEqual(calls, [])

    def test_unlisted_stale_screenshot_cannot_be_uploaded(self):
        with TemporaryDirectory() as tmp:
            config, manifest = self.creative_fixture(Path(tmp))
            path = config.output_root / "iphone"
            path.mkdir()
            for name in ("01.png", "stale.png"):
                (path / name).touch()
            manifest["locales"] = {"default": {"iphone": [{"filename": "01.png"}]}}
            (config.output_root / "asc_upload.json").write_text(json.dumps(manifest))
            calls = []
            with self.assertRaisesRegex(SystemExit, "differs from manifest"):
                upload_screenshots(config, runner=self.fake_asc_runner(calls))
            self.assertEqual(calls, [])

    def test_target_settings_change_fingerprint_with_explicit_design_inputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.png").touch()
            path = root / ".asc-screens-ci.json"
            payload = {"app_id": "123", "version": "1.2.3", "design_inputs": ["source.png"]}
            path.write_text(json.dumps(payload))
            first = load_ci_config(path).fingerprint
            payload["default_locale"] = "en-GB"
            path.write_text(json.dumps(payload))
            second = load_ci_config(path).fingerprint
            payload["creative_asset_target"] = {"kind": "version"}
            path.write_text(json.dumps(payload))
            third = load_ci_config(path).fingerprint
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)

    def test_nested_renderer_source_is_fingerprinted_at_its_actual_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "design"
            nested.mkdir()
            (nested / "source.png").write_text("before")
            (nested / "screens.json").write_text(json.dumps({"source": "source.png"}))
            path = root / ".asc-screens-ci.json"
            path.write_text(json.dumps({"asc_screens_config": "design/screens.json"}))
            first = load_ci_config(path).fingerprint
            (nested / "source.png").write_text("after")
            second = load_ci_config(path).fingerprint
        self.assertNotEqual(first, second)

    def test_nested_renderer_output_is_resolved_at_renderer_config(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "design"
            nested.mkdir()
            (nested / "screens.json").write_text(json.dumps({"source": "source.png", "output_root": "exports"}))
            path = root / ".asc-screens-ci.json"
            path.write_text(json.dumps({"asc_screens_config": "design/screens.json"}))
            self.assertEqual(load_ci_config(path).output_root, nested / "exports")

    def test_nested_design_copy_and_icon_both_change_default_fingerprint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            renderer = root / "renderer"
            artwork = renderer / "artwork"
            brand = renderer / "brand"
            artwork.mkdir(parents=True)
            brand.mkdir()
            (renderer / "source.png").write_bytes(b"screenshot")
            icon = brand / "app.png"
            icon.write_bytes(b"first icon")
            design = artwork / "header.json"
            design_payload = {"title": "Before", "icon": "../brand/app.png"}
            design.write_text(json.dumps(design_payload))
            (renderer / "screens.json").write_text(json.dumps({"source": "source.png", "design_file": "artwork/header.json"}))
            path = root / ".asc-screens-ci.json"
            path.write_text(json.dumps({"asc_screens_config": "renderer/screens.json"}))

            initial = load_ci_config(path)
            design_payload["title"] = "After"
            design.write_text(json.dumps(design_payload))
            changed_copy = load_ci_config(path)
            icon.write_bytes(b"second icon")
            changed_icon = load_ci_config(path)

            self.assertIn(str(design), initial.design_inputs)
            self.assertIn(icon.resolve(), [Path(entry).resolve() for entry in initial.design_inputs])
            self.assertNotEqual(initial.fingerprint, changed_copy.fingerprint)
            self.assertNotEqual(changed_copy.fingerprint, changed_icon.fingerprint)

    def test_environment_icon_path_tracks_bytes_and_selected_location(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            (first / "icon.png").write_bytes(b"first icon")
            (second / "icon.png").write_bytes(b"second icon")
            (root / "asc-screens.json").write_text(json.dumps({"design_file": "design.json"}))
            (root / "design.json").write_text(json.dumps({"icon": "$ASC_TEST_ICONS/icon.png"}))
            path = root / ".asc-screens-ci.json"
            path.write_text("{}")
            with patch.dict("os.environ", {"ASC_TEST_ICONS": str(first)}):
                initial = load_ci_config(path)
                self.assertIn(str(first / "icon.png"), initial.design_inputs)
                (first / "icon.png").write_bytes(b"changed icon")
                changed = load_ci_config(path)
            with patch.dict("os.environ", {"ASC_TEST_ICONS": str(second)}):
                relocated = load_ci_config(path)
            self.assertNotEqual(initial.fingerprint, changed.fingerprint)
            self.assertNotEqual(changed.fingerprint, relocated.fingerprint)

    def test_missing_design_icon_is_fingerprinted_until_it_is_available(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "asc-screens.json").write_text(json.dumps({"design_file": "design.json"}))
            (root / "design.json").write_text(json.dumps({"icon": "icon.png"}))
            path = root / ".asc-screens-ci.json"
            path.write_text("{}")

            missing = load_ci_config(path)
            self.assertIn(str(root / "icon.png"), missing.design_inputs)
            (root / "icon.png").write_bytes(b"new icon")
            self.assertNotEqual(missing.fingerprint, load_ci_config(path).fingerprint)

    def test_explicit_design_inputs_do_not_discover_design_references(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.png").write_bytes(b"source")
            (root / "asc-screens.json").write_text(json.dumps({"source": "source.png", "design_file": "design.json"}))
            (root / "design.json").write_text(json.dumps({"title": "Before", "icon": "icon.png"}))
            (root / "icon.png").write_bytes(b"first icon")
            path = root / ".asc-screens-ci.json"
            path.write_text(json.dumps({"design_inputs": ["source.png"]}))

            initial = load_ci_config(path)
            (root / "design.json").write_text(json.dumps({"title": "After", "icon": "missing.png"}))
            (root / "icon.png").write_bytes(b"second icon")
            self.assertEqual(initial.design_inputs, ("source.png",))
            self.assertEqual(initial.fingerprint, load_ci_config(path).fingerprint)

    def test_default_source_fingerprint_excludes_outputs_and_cache_but_explicit_inputs_do_not(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.png").write_text("source")
            (root / "asc-screens.json").write_text(json.dumps({"source": ".", "output_root": "exports"}))
            path = root / ".asc-screens-ci.json"
            payload = {"app_id": "123", "version": "1.2.3"}
            path.write_text(json.dumps(payload))
            first = load_ci_config(path).fingerprint
            for directory in ("exports", ".asc-screens-cache", ".git", "__pycache__"):
                (root / directory).mkdir()
                (root / directory / "generated").write_text("generated")
            second = load_ci_config(path).fingerprint
            self.assertEqual(first, second)
            payload["design_inputs"] = ["."]
            path.write_text(json.dumps(payload))
            explicit_first = load_ci_config(path).fingerprint
            (root / "exports" / "generated").write_text("changed")
            explicit_second = load_ci_config(path).fingerprint
            self.assertNotEqual(explicit_first, explicit_second)

    def test_default_source_fingerprint_excludes_custom_cache_dir(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "asc-screens.json").write_text(json.dumps({"source": ".", "output_root": "exports"}))
            path = root / ".asc-screens-ci.json"
            path.write_text(json.dumps({"app_id": "123", "version": "1.2.3"}))
            cache = root / "ci-cache"
            first = load_ci_config(path, cache_dir=cache).fingerprint
            cache.mkdir()
            (cache / "marker.done").touch()
            self.assertEqual(first, load_ci_config(path, cache_dir=cache).fingerprint)


if __name__ == "__main__":
    unittest.main()
