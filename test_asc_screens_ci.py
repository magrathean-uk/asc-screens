import dataclasses
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asc_creative import RUN_ID_ENV
from asc_screens_ci import (
    compute_design_fingerprint,
    load_ci_config,
    run_ci,
    upload_screenshots,
)


def seal(out, manifest):
    """Add the sha256 a real build records for every listed file that exists, as the renderer would."""
    out = Path(out)
    for locale, families in manifest.get("locales", {}).items():
        for family, entries in families.items():
            directory = out / family if locale == "default" else out / locale / family
            for entry in entries:
                file = directory / entry["filename"]
                if file.is_file():
                    entry.setdefault("sha256", hashlib.sha256(file.read_bytes()).hexdigest())
    for entry in manifest.get("creative_assets", []):
        file = Path(entry["path"])
        if file.is_file():
            entry.setdefault("sha256", hashlib.sha256(file.read_bytes()).hexdigest())
    return manifest


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
        self.assertEqual(config.device_type_map["mac"], "DESKTOP")

    def test_default_design_inputs_include_mac_wallpaper_and_icon_but_not_bundles(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            asc_config = root / "asc-screens.json"
            asc_config.write_text(json.dumps({"source": "shots", "mac_wallpaper": "wall.png", "mac_app": "icon.png"}), encoding="utf-8")
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3"}), encoding="utf-8")
            with_icon = load_ci_config(ci_config).design_inputs
            asc_config.write_text(json.dumps({"source": "shots", "mac_app": "/Applications/Tescam.app"}), encoding="utf-8")
            with_bundle = load_ci_config(ci_config).design_inputs

        self.assertEqual([Path(value).name for value in with_icon[1:]], ["shots", "wall.png", "icon.png"])
        self.assertEqual([value.split("Tescam.app/")[-1] for value in with_bundle[1:]],
                         [str(Path(tmp).resolve() / "shots"), "Contents/Info.plist", "Contents/Resources/*.icns",
                          "Contents/Resources/Assets.car"])

    def test_mac_screenshots_need_a_mac_os_version_before_anything_uploads(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, manifest = self.creative_fixture(root)
            sets = {}
            for family in ("iphone", "mac"):
                path = config.output_root / family
                path.mkdir()
                (path / "01.png").touch()
                sets[family] = [{"filename": "01.png", "path": str(path / "01.png")}]
            manifest["locales"] = {"default": sets}
            (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
            calls = []
            with self.assertRaisesRegex(SystemExit, "mac screenshots cannot upload to a IOS version"):
                upload_screenshots(config, runner=self.fake_asc_runner(calls))
            self.assertEqual(calls, [])

    def test_upload_screenshots_runs_asc_commands_from_manifest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            (out / "en-GB" / "iphone").mkdir(parents=True)
            (out / "en-GB" / "iphone" / "01.png").touch()
            (out / "asc_upload.json").write_text(
                json.dumps(
                    seal(out, {
                        "locales": {
                            "en-GB": {
                                "iphone": [
                                    {"slot": 1, "filename": "01.png", "path": str(out / "en-GB" / "iphone" / "01.png")}
                                ]
                            }
                        }
                    })
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
                json.dumps(seal(out, {"locales": {"default": {"iphone": [{"slot": 1, "filename": "01.png", "path": str(out / "iphone" / "01.png")}]}}})),
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
                        json.dumps(seal(out, {"run_id": kwargs["env"][RUN_ID_ENV],
                                    "locales": {"en-GB": {"iphone": [{"slot": 1, "filename": "01.png", "path": str(out / "en-GB" / "iphone" / "01.png")}]}}})),
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
        (out / "asc_upload.json").write_text(json.dumps(seal(out, manifest)), encoding="utf-8")
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
            (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
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
                (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
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
            (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
            config = dataclasses.replace(config, device_type_map={**config.device_type_map, "mac": ""})
            calls = []
            with self.assertRaisesRegex(SystemExit, "device_type_map.*mac"):
                upload_screenshots(config, runner=self.fake_asc_runner(calls))
            self.assertEqual(calls, [])

    def screenshot_fixture(self, root, family, platform="IOS", device_type_map=None):
        config, manifest = self.creative_fixture(root)
        path = config.output_root / family
        path.mkdir()
        (path / "01.png").touch()
        manifest["creative_assets"] = []
        manifest["locales"] = {"default": {family: [{"filename": "01.png", "path": str(path / "01.png")}]}}
        (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
        return dataclasses.replace(config, platform=platform, device_type_map={**config.device_type_map, **(device_type_map or {})})

    def test_screenshot_families_only_upload_to_their_own_platform(self):
        for family, platform in (("iphone", "TV_OS"), ("iphone", "VISION_OS"), ("ipad", "TV_OS"), ("ipad", "VISION_OS"),
                                 ("iphone", "MAC_OS"), ("ipad", "MAC_OS"), ("mac", "IOS"), ("mac", "VISION_OS")):
            with self.subTest(family=family, platform=platform), TemporaryDirectory() as tmp:
                config = self.screenshot_fixture(Path(tmp), family, platform)
                calls = []
                with self.assertRaisesRegex(SystemExit, f"{family} screenshots cannot upload to a {platform} version"):
                    upload_screenshots(config, runner=self.fake_asc_runner(calls))
                self.assertEqual(calls, [])
                with self.assertRaisesRegex(SystemExit, "cannot upload"):
                    run_ci(config, dry_run=True)

    def test_device_type_must_belong_to_the_screenshot_family(self):
        for family, platform, device_type in (("ipad", "IOS", "IPHONE_69"), ("mac", "MAC_OS", "IPHONE_69"),
                                              ("iphone", "IOS", "IPAD_PRO_3GEN_129"), ("iphone", "IOS", "DESKTOP"),
                                              ("ipad", "IOS", "DESKTOP"), ("mac", "MAC_OS", "IPAD_PRO_3GEN_129"),
                                              ("iphone", "IOS", "APP_IPAD_105")):
            with self.subTest(family=family, device_type=device_type), TemporaryDirectory() as tmp:
                config = self.screenshot_fixture(Path(tmp), family, platform, {family: device_type})
                calls = []
                with self.assertRaisesRegex(SystemExit, f"{device_type}.*not a {family} device type"):
                    upload_screenshots(config, runner=self.fake_asc_runner(calls))
                self.assertEqual(calls, [])
                with self.assertRaisesRegex(SystemExit, "not a .* device type"):
                    run_ci(config, dry_run=True)

    def test_device_type_whitespace_is_not_sent_to_asc(self):
        with TemporaryDirectory() as tmp:
            config = self.screenshot_fixture(Path(tmp), "iphone", "IOS", {"iphone": " IPHONE_67 "})
            command = run_ci(config, dry_run=True)["commands"][0]
        self.assertEqual(command[command.index("--device-type") + 1], "IPHONE_67")

    def test_same_family_device_type_overrides_still_work(self):
        for family, platform, device_type in (("iphone", "IOS", "IPHONE_67"), ("iphone", "IOS", "APP_IPHONE_65"), ("iphone", "IOS", "IMESSAGE_APP_IPHONE_67"),
                                              ("ipad", "IOS", "IPAD_PRO_3GEN_11"), ("mac", "MAC_OS", "DESKTOP")):
            with self.subTest(family=family, device_type=device_type), TemporaryDirectory() as tmp:
                config = self.screenshot_fixture(Path(tmp), family, platform, {family: device_type})
                plan = run_ci(config, dry_run=True)
                command = plan["commands"][0]
                self.assertEqual(command[command.index("--device-type") + 1], device_type)

    def test_unsupported_device_types_are_refused_before_any_command(self):
        # asc 5.14.3 rejects each of these locally; a prefix match let them into the plan.
        for family, platform, device_type in (("iphone", "IOS", "IPHONE_999"), ("ipad", "IOS", "IPAD_BOGUS"),
                                              ("iphone", "IOS", "IMESSAGE_APP_DESKTOP"), ("mac", "MAC_OS", "IMESSAGE_APP_DESKTOP"),
                                              ("iphone", "IOS", "APP_WATCH_SERIES_10"), ("iphone", "IOS", "")):
            with self.subTest(device_type=device_type), TemporaryDirectory() as tmp:
                config = self.screenshot_fixture(Path(tmp), family, platform, {family: device_type})
                calls = []
                with self.assertRaises(SystemExit):
                    upload_screenshots(config, runner=self.fake_asc_runner(calls))
                self.assertEqual(calls, [])
                with self.assertRaises(SystemExit):
                    run_ci(config, dry_run=True)

    def test_unsupported_slot_message_names_the_canonical_type(self):
        with TemporaryDirectory() as tmp:
            config = self.screenshot_fixture(Path(tmp), "iphone", "IOS", {"iphone": "iphone_999"})
            with self.assertRaisesRegex(SystemExit, "APP_IPHONE_999 is not a supported iphone screenshot slot"):
                run_ci(config, dry_run=True)

    def test_device_types_are_canonicalised_the_way_asc_does(self):
        for family, platform, device_type in (("iphone", "IOS", "iphone_67"), ("iphone", "IOS", " app_iphone_69 "),
                                              ("ipad", "IOS", "ipad_pro_3gen_129"), ("mac", "MAC_OS", "desktop"),
                                              ("mac", "MAC_OS", "App_Desktop"), ("iphone", "IOS", "imessage_app_iphone_61")):
            with self.subTest(device_type=device_type), TemporaryDirectory() as tmp:
                config = self.screenshot_fixture(Path(tmp), family, platform, {family: device_type})
                command = run_ci(config, dry_run=True)["commands"][0]
                self.assertEqual(command[command.index("--device-type") + 1], device_type.strip())

    @unittest.skipUnless(shutil.which("asc"), "asc is not installed")
    def test_supported_slots_match_the_local_asc_catalogue(self):
        # Local, read-only catalogue; no account call. A newer asc that adds slots should fail here.
        from asc_screens_ci import SUPPORTED_SCREENSHOT_SLOTS

        result = subprocess.run(["asc", "screenshots", "sizes", "--all", "--output", "json"], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            self.skipTest("asc screenshots sizes --all is not available")
        catalogue = {item["displayType"] for item in json.loads(result.stdout)["sizes"]}
        ours = set().union(*SUPPORTED_SCREENSHOT_SLOTS.values())
        self.assertEqual(ours - catalogue, set(), "slots asc no longer lists")
        phone_pad_mac = {name for name in catalogue if "IPHONE_" in name or "IPAD_" in name or name == "APP_DESKTOP"}
        self.assertEqual(phone_pad_mac - ours, set(), "slots asc lists that this tool does not offer")

    def test_mixed_plan_with_one_unsupported_slot_runs_no_command(self):
        # A valid iPad set sorts before the invalid iPhone slot; it must not be replaced first.
        with TemporaryDirectory() as tmp:
            config = self.screenshot_fixture(Path(tmp), "ipad", "IOS")
            (config.output_root / "iphone").mkdir()
            (config.output_root / "iphone" / "01.png").touch()
            manifest = json.loads((config.output_root / "asc_upload.json").read_text())
            manifest["locales"]["default"]["iphone"] = [{"filename": "01.png"}]
            (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
            config = dataclasses.replace(config, device_type_map={**config.device_type_map, "iphone": "IPHONE_999"})
            calls = []
            with self.assertRaisesRegex(SystemExit, "IPHONE_999"):
                upload_screenshots(config, runner=self.fake_asc_runner(calls))
            self.assertEqual(calls, [])

    def test_run_ci_never_uploads_a_manifest_the_current_build_did_not_write(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            (root / "asc-screens.json").write_text(json.dumps({"source": "shots", "output_root": "out"}), encoding="utf-8")
            (root / "shots").mkdir()
            (root / "shots" / "one.png").write_text("new", encoding="utf-8")
            (out / "ipad").mkdir(parents=True)
            (out / "ipad" / "01.png").touch()
            (out / "asc_upload.json").write_text(
                json.dumps(seal(out, {"locales": {"default": {"ipad": [{"slot": 1, "filename": "01.png", "path": str(out / "ipad" / "01.png")}]}}})),
                encoding="utf-8",
            )
            ci_config = root / ".asc-screens-ci.json"
            ci_config.write_text(json.dumps({"app_id": "123", "version": "1.2.3", "asc_screens_config": "asc-screens.json"}), encoding="utf-8")
            config = load_ci_config(ci_config)
            calls = []

            def runner(cmd, **kwargs):
                # The build "succeeds" but writes nothing, as when every input is skipped.
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "not written by this run"):
                run_ci(config, cache_dir=root / ".asc-screens-cache", runner=runner)

            self.assertEqual([cmd[0] for cmd in calls], ["asc-screens"])
            self.assertTrue((out / "asc_upload.json").exists(), "the previous handoff is left alone")
            self.assertFalse((root / ".asc-screens-cache" / f"{config.cache_key}.done").exists())

    def run_fixture(self, root, device_type_map=None):
        out = root / "out"
        (root / "asc-screens.json").write_text(json.dumps({"source": "shots", "output_root": "out"}), encoding="utf-8")
        (root / "shots").mkdir()
        (root / "shots" / "one.png").write_text("new", encoding="utf-8")
        payload = {"app_id": "1001", "version": "1.2.3", "asc_screens_config": "asc-screens.json", "default_locale": "en-GB"}
        if device_type_map:
            payload["device_type_map"] = device_type_map
        (root / ".asc-screens-ci.json").write_text(json.dumps(payload), encoding="utf-8")
        return load_ci_config(root / ".asc-screens-ci.json"), out

    @staticmethod
    def write_build(out, family, run_id):
        (out / family).mkdir(parents=True, exist_ok=True)
        (out / family / "01.png").touch()
        (out / "asc_upload.json").write_text(json.dumps(seal(out,
            {"run_id": run_id, "locales": {"default": {family: [{"slot": 1, "filename": "01.png", "path": str(out / family / "01.png")}]}}})),
            encoding="utf-8")

    def test_a_run_refuses_a_manifest_another_run_wrote_to_the_shared_root(self):
        # Run A builds iPhone screenshots; run B writes iPad output into the same root before A
        # reaches preflight. A must refuse rather than replace sets from B's build.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, out = self.run_fixture(root)
            calls = []

            def runner(cmd, **kwargs):
                calls.append(cmd)
                if cmd[:1] == ["asc-screens"]:
                    self.write_build(out, "iphone", kwargs["env"][RUN_ID_ENV])
                    self.write_build(out, "ipad", "run-b")
                return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

            with self.assertRaisesRegex(SystemExit, "not written by this run"):
                run_ci(config, cache_dir=root / ".asc-screens-cache", runner=runner)
            self.assertEqual([cmd[0] for cmd in calls], ["asc-screens"])
            self.assertFalse((root / ".asc-screens-cache" / f"{config.cache_key}.done").exists())

    def test_a_run_refuses_a_manifest_replaced_while_it_looks_up_the_version(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, out = self.run_fixture(root)
            calls = []
            base = self.fake_asc_runner(calls)

            def runner(cmd, **kwargs):
                if cmd[:1] == ["asc-screens"]:
                    calls.append(cmd)
                    self.write_build(out, "iphone", kwargs["env"][RUN_ID_ENV])
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                if cmd[1:3] == ["localizations", "list"]:
                    self.write_build(out, "ipad", "run-b")
                return base(cmd, **kwargs)

            with self.assertRaisesRegex(SystemExit, "changed while|not written by this run"):
                run_ci(config, cache_dir=root / ".asc-screens-cache", runner=runner)
            self.assertFalse([cmd for cmd in calls if "--replace" in cmd])

    def test_unreadable_manifest_is_a_clean_refusal(self):
        for text in ('{"locales": {', "[]", ""):
            with self.subTest(text=text), TemporaryDirectory() as tmp:
                config = self.screenshot_fixture(Path(tmp), "iphone")
                (config.output_root / "asc_upload.json").write_text(text)
                calls = []
                for kwargs in ({"run_id": None}, {"run_id": "abc"}):
                    with self.assertRaisesRegex(SystemExit, "unreadable|not a JSON object"):
                        upload_screenshots(config, runner=self.fake_asc_runner(calls), **kwargs)
                self.assertEqual(calls, [])

    def test_each_run_gets_its_own_run_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, out = self.run_fixture(root)
            ids = []

            def runner(cmd, **kwargs):
                if cmd[:1] == ["asc-screens"]:
                    ids.append(kwargs["env"][RUN_ID_ENV])
                    self.write_build(out, "iphone", ids[-1])
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                return self.fake_asc_runner([])(cmd, **kwargs)

            for _ in range(2):
                run_ci(config, cache_dir=root / ".asc-screens-cache", force=True, runner=runner)
            self.assertEqual(len(set(ids)), 2)
            self.assertTrue(all(len(value) >= 16 for value in ids))

    def test_manifest_without_a_run_id_still_passes_the_documented_manual_flows(self):
        # Existing-manifest dry run and a direct upload_screenshots call have no run to own the file.
        with TemporaryDirectory() as tmp:
            config = self.screenshot_fixture(Path(tmp), "iphone")
            self.assertTrue(run_ci(config, dry_run=True)["commands"])
            calls = []
            upload_screenshots(config, runner=self.fake_asc_runner(calls))
            self.assertTrue([cmd for cmd in calls if "--replace" in cmd])

    def test_unlisted_stale_screenshot_cannot_be_uploaded(self):
        with TemporaryDirectory() as tmp:
            config, manifest = self.creative_fixture(Path(tmp))
            path = config.output_root / "iphone"
            path.mkdir()
            for name in ("01.png", "stale.png"):
                (path / name).touch()
            manifest["locales"] = {"default": {"iphone": [{"filename": "01.png"}]}}
            (config.output_root / "asc_upload.json").write_text(json.dumps(seal(config.output_root, manifest)))
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



class ManifestContentBindingTests(unittest.TestCase):
    """The manifest is bound to the bytes it listed, and written atomically."""

    @staticmethod
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def config_for(self, root):
        (root / ".asc-screens-ci.json").write_text(
            json.dumps({"app_id": "123", "version": "1.2.3", "output_root": "out", "default_locale": "en-GB"}), encoding="utf-8")
        return load_ci_config(root / ".asc-screens-ci.json")

    def runner(self, calls):
        return AscScreensCiTests().fake_asc_runner(calls)

    def build_screenshots(self, root, content):
        """One real renderer run (rendering mocked) into root/out; returns the output root."""
        import asc_screens

        source = root / "src"
        (source / "iphone").mkdir(parents=True, exist_ok=True)
        (source / "iphone" / "01.png").touch()
        out = root / "out"
        shot = out / "iphone" / "01.png"

        def render(*args, **kwargs):
            shot.parent.mkdir(parents=True, exist_ok=True)
            shot.write_bytes(content)
            return [shot]

        argv = ["asc-screens", str(source), "--kind", "iphone", "--background", "#101010,#202020,#303030",
                "--output-root", str(out)]
        with patch("sys.argv", argv), patch("sys.stdout", new_callable=io.StringIO), \
                patch("asc_screens.shutil.which", return_value="/usr/bin/magick"), \
                patch("asc_screens.require_frames_bin", return_value=Path("frames")), \
                patch("asc_screens.frame_inputs", return_value=[]), \
                patch("asc_screens.process_kind", side_effect=render):
            asc_screens.main()
        return out

    def test_failed_rebuild_that_changed_a_screenshot_is_refused_by_dry_run_and_upload(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = self.build_screenshots(root, b"red")
            config = self.config_for(root)
            self.assertTrue(run_ci(config, dry_run=True)["commands"])
            # The rebuild renders blue into the same final path, then fails writing the contact sheet.
            (out / "asc_review.html").unlink()
            (out / "asc_review.html").mkdir()
            with self.assertRaises((IsADirectoryError, PermissionError)):
                self.build_screenshots(root, b"blue")
            self.assertEqual((out / "iphone" / "01.png").read_bytes(), b"blue")
            calls = []
            with self.assertRaisesRegex(SystemExit, r"01\.png.*changed since the manifest"):
                run_ci(config, dry_run=True)
            with self.assertRaisesRegex(SystemExit, r"01\.png.*changed since the manifest"):
                upload_screenshots(config, runner=self.runner(calls))
            self.assertEqual(calls, [])

    def test_screenshot_manifest_entry_without_a_hash_is_refused_with_a_rebuild_message(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = self.build_screenshots(root, b"red")
            manifest = json.loads((out / "asc_upload.json").read_text(encoding="utf-8"))
            del manifest["locales"]["default"]["iphone"][0]["sha256"]
            (out / "asc_upload.json").write_text(json.dumps(manifest), encoding="utf-8")
            config = self.config_for(root)
            calls = []
            with self.assertRaisesRegex(SystemExit, r"01\.png.*no sha256.*rebuild"):
                run_ci(config, dry_run=True)
            with self.assertRaisesRegex(SystemExit, r"01\.png.*no sha256.*rebuild"):
                upload_screenshots(config, runner=self.runner(calls))
            self.assertEqual(calls, [])

    def creative_manifest(self, root, **entry_fields):
        out = root / "out"
        out.mkdir()
        asset = out / "header.png"
        asset.write_bytes(b"original")
        entry = {"profile": "header", "media_type": "image", "path": str(asset), "locale": "default",
                 "placements": ["PRODUCT_PAGE_HEADER_ASSET"], "sha256": self.sha(asset), **entry_fields}
        entry = {key: value for key, value in entry.items() if value is not None}
        (out / "asc_upload.json").write_text(json.dumps({"locales": {}, "creative_assets": [entry]}), encoding="utf-8")
        return asset

    def test_creative_asset_changed_after_its_manifest_was_written_is_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = self.creative_manifest(root)
            config = self.config_for(root)
            self.assertTrue(run_ci(config, dry_run=True)["commands"])
            asset.write_bytes(b"changed")
            calls = []
            with self.assertRaisesRegex(SystemExit, r"header\.png.*changed since the manifest"):
                run_ci(config, dry_run=True)
            with self.assertRaisesRegex(SystemExit, r"header\.png.*changed since the manifest"):
                upload_screenshots(config, runner=self.runner(calls))
            self.assertEqual(calls, [])

    def test_creative_asset_without_a_hash_is_refused_with_a_rebuild_message(self):
        for value in (None, "", 7):
            with self.subTest(sha256=value), TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.creative_manifest(root, sha256=value)
                config = self.config_for(root)
                if value is None:
                    expected = r"header\.png.*no sha256.*rebuild"
                else:
                    expected = r"header\.png.*(no sha256|changed since the manifest)"
                calls = []
                with self.assertRaisesRegex(SystemExit, expected):
                    run_ci(config, dry_run=True)
                with self.assertRaisesRegex(SystemExit, expected):
                    upload_screenshots(config, runner=self.runner(calls))
                self.assertEqual(calls, [])

    def test_a_file_changed_while_the_run_looks_up_the_version_is_not_replaced(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = self.build_screenshots(root, b"red")
            config = self.config_for(root)
            calls = []
            base = self.runner(calls)

            def runner(cmd, **kwargs):
                if cmd[1:3] == ["localizations", "list"]:
                    (out / "iphone" / "01.png").write_bytes(b"blue")
                return base(cmd, **kwargs)

            with self.assertRaisesRegex(SystemExit, r"01\.png.*changed since the manifest"):
                upload_screenshots(config, runner=runner)
            self.assertFalse([cmd for cmd in calls if "--replace" in cmd])

    def test_creative_exporter_records_the_hash_of_each_final_asset(self):
        import asc_creative

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(b"original")
            output = root / "exports"

            def compose(source_path, staged_path, size, design):
                Path(staged_path).write_bytes(b"composed")
                return {"title": "t", "output": str(staged_path), "validated": True}

            with patch("asc_design.render_design", side_effect=compose), \
                    patch.object(asc_creative, "validate_creative_file", return_value=()):
                files = asc_creative.process_creative_assets(source, output, "header", design={"app_name": "A", "title": "t"})
            for name in ("asc_upload.json", "asc_creative_review.json"):
                entries = json.loads((output / name).read_text(encoding="utf-8"))["creative_assets"]
                self.assertEqual([entry["sha256"] for entry in entries], [self.sha(path) for path in files])
            config = self.config_for(root)
            config = dataclasses.replace(config, output_root=output.resolve())
            self.assertTrue(run_ci(config, dry_run=True)["commands"])


class AtomicManifestWriteTests(unittest.TestCase):
    def outputs(self, root):
        shot = root / "iphone" / "01.png"
        shot.parent.mkdir(parents=True)
        shot.write_bytes(b"png")
        return [shot]

    def test_a_symlinked_manifest_is_replaced_not_followed(self):
        from asc_screens import write_review_manifest, write_upload_manifest

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            outputs = self.outputs(root)
            archive = Path(tmp) / "archive"
            archive.mkdir()
            for name, write in (("asc_upload.json", write_upload_manifest), ("asc_review.json", write_review_manifest)):
                target = archive / name
                target.write_text("reviewed handoff", encoding="utf-8")
                (root / name).symlink_to(target)
                write(root, outputs)
                self.assertEqual(target.read_text(encoding="utf-8"), "reviewed handoff", name)
                self.assertFalse((root / name).is_symlink(), name)
                self.assertIn("items" if "review" in name else "locales", json.loads((root / name).read_text(encoding="utf-8")))

    def test_a_write_failure_leaves_the_previous_manifest_byte_identical(self):
        resource = __import__("resource") if importlib.util.find_spec("resource") else None
        if resource is None:
            self.skipTest("needs POSIX resource limits")
        import signal
        from asc_screens import write_review_manifest, write_upload_manifest

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            outputs = self.outputs(root)
            previous = b'{"previous": "' + b"x" * 60 + b'"}'
            soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
            old_handler = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            try:
                for name, write in (("asc_upload.json", write_upload_manifest), ("asc_review.json", write_review_manifest)):
                    (root / name).write_bytes(previous)
                    resource.setrlimit(resource.RLIMIT_FSIZE, (16, hard))
                    try:
                        with self.assertRaises(OSError):
                            write(root, outputs)
                    finally:
                        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
                    self.assertEqual((root / name).read_bytes(), previous, name)
            finally:
                signal.signal(signal.SIGXFSZ, old_handler)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["asc_review.json", "asc_upload.json", "iphone"])

    def test_a_failed_replace_leaves_the_previous_manifest_and_no_temporary_file(self):
        from asc_screens import write_upload_manifest

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            outputs = self.outputs(root)
            (root / "asc_upload.json").write_text("previous", encoding="utf-8")
            with patch("os.replace", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    write_upload_manifest(root, outputs)
            self.assertEqual((root / "asc_upload.json").read_text(encoding="utf-8"), "previous")
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["asc_upload.json", "iphone"])


if __name__ == "__main__":
    unittest.main()
