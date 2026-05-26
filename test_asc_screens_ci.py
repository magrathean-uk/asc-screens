import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from asc_screens_ci import (
    compute_design_fingerprint,
    load_ci_config,
    run_ci,
    upload_screenshots,
)


class AscScreensCiTests(unittest.TestCase):
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

        self.assertEqual(config.design_inputs, ("asc-screens.json", "shots", "copy.json"))
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
        self.assertIn(["asc", "versions", "list", "--app", "123", "--output", "json"], calls)
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

        self.assertIn(["asc", "localizations", "list", "--version", "v1", "--output", "json", "--locale", "en-GB"], calls)

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


if __name__ == "__main__":
    unittest.main()
