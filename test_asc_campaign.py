import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import asc_campaign as campaign


class CampaignTests(unittest.TestCase):
    def recipe(self, root):
        (root / "source.webp").write_bytes(b"original capture")
        (root / "icon.png").write_bytes(b"original icon")
        data = {"schema_version": 1, "defaults": {"locale": "en-GB"}, "apps": [
            {"id": "nodex", "name": "Nodex", "design": {
                "app_name": "Nodex", "title": "Servers in sight", "icon": "icon.png"},
             "features": [{"id": "hero", "source": "source.webp", "crop": [10, 20, 80, 60],
                           "rationale": "Readable server trends", "profiles": ["header", "search-results"]}]},
            {"id": "termex", "name": "Termex", "design": {
                "app_name": "Termex", "title": "Move files"},
             "features": [{"id": "files", "source": "source.webp", "rationale": "Clear SFTP benefit"}]}]}
        path = root / "portfolio.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path, data

    def test_paths_filters_and_overrides(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _ = self.recipe(root)
            loaded = campaign.load_campaign(config, ["nodex"], "universal")
            self.assertEqual(len(loaded["apps"]), 1)
            feature = loaded["apps"][0]["features"][0]
            self.assertEqual(feature["source"], str(root / "source.webp"))
            self.assertEqual(feature["design"]["icon"], str(root / "icon.png"))
            self.assertEqual(feature["profiles"], ["universal"])
            all_profiles = campaign.load_campaign(config, ["nodex"], "creative-all")
            self.assertEqual(all_profiles["apps"][0]["features"][0]["profiles"], list(campaign.CREATIVE_PROFILES))
            with self.assertRaisesRegex(ValueError, "Unknown app"):
                campaign.load_campaign(config, ["other"])

    def test_defaults_and_feature_copy_override(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, data = self.recipe(root)
            data["apps"][1]["features"][0]["design"] = {"title": "Files within reach", "style": "dark"}
            config.write_text(json.dumps(data))
            feature = campaign.load_campaign(config, ["termex"])["apps"][0]["features"][0]
            self.assertEqual(feature["design"]["title"], "Files within reach")
            self.assertEqual(feature["design"]["style"], "dark")
            self.assertEqual(feature["profiles"], list(campaign.DEFAULT_PROFILES))

    def test_frame_assets_environment_variable_is_resolved_before_validation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, data = self.recipe(root)
            assets = root / "library" / "frames"
            assets.mkdir(parents=True)
            data["apps"][0]["design"]["frame_assets"] = "$ASC_TEST_FRAME_LIBRARY/frames"
            data["apps"][0]["design"]["icon"] = "$ASC_TEST_ICON_ROOT/icon.png"
            config.write_text(json.dumps(data))
            with patch.dict("os.environ", {"ASC_TEST_FRAME_LIBRARY": str(root / "library"),
                                           "ASC_TEST_ICON_ROOT": str(root)}):
                loaded = campaign.load_campaign(config, ["nodex"])
            self.assertEqual(loaded["apps"][0]["features"][0]["design"]["frame_assets"], str(assets))
            self.assertEqual(loaded["apps"][0]["features"][0]["design"]["icon"], str(root / "icon.png"))

    def test_bad_schema_ids_duplicates_sources_and_design_are_rejected(self):
        mutations = [
            lambda data: data.update(schema_version=True),
            lambda data: data.update(apps=[]),
            lambda data: data["apps"][0].update(id="../nodex"),
            lambda data: data["apps"][1].update(id="nodex"),
            lambda data: data["apps"][0]["features"].append(dict(data["apps"][0]["features"][0])),
            lambda data: data["apps"][0]["features"][0].update(source="missing.png"),
            lambda data: data["apps"][0]["features"][0].update(source="clip.mov"),
            lambda data: data["apps"][0]["features"][0].update(profiles=["screenshots"]),
            lambda data: data["apps"][0]["features"][0].update(profiles=["header", "header"]),
            lambda data: data["apps"][0]["features"][0].update(crop=[0, 0, True, 10]),
            lambda data: data["apps"][0]["features"][0].update(crop=[-1, 0, 10, 10]),
            lambda data: data["apps"][0]["design"].update(title=""),
            lambda data: data["apps"][0]["design"].update(style="neon"),
            lambda data: data["apps"][0]["design"].update(icon="missing.png"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), TemporaryDirectory() as temporary:
                root = Path(temporary)
                config, data = self.recipe(root)
                (root / "clip.mov").write_bytes(b"video")
                mutation(data)
                config.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    campaign.load_campaign(config)

    def test_list_is_read_only_and_does_not_probe_images(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _ = self.recipe(root)
            output = root / "exports"
            with patch.object(campaign, "_run") as run, contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(campaign.main(["--config", str(config), "--app", "nodex", "--list",
                                                "--output-root", str(output)]), 0)
            run.assert_not_called()
            self.assertEqual(json.loads(stdout.getvalue())["apps"][0]["id"], "nodex")
            self.assertFalse(output.exists())

    def test_all_crop_bounds_are_checked_before_generation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, data = self.recipe(root)
            data["apps"][1]["features"][0]["crop"] = [90, 0, 20, 20]
            config.write_text(json.dumps(data))
            output = root / "exports"
            with patch.object(campaign, "_oriented_size", return_value=(100, 100)), \
                    patch.object(campaign, "_normalise_source") as normalise, \
                    patch.object(campaign, "process_creative_assets") as render:
                with self.assertRaisesRegex(ValueError, "exceeds oriented"):
                    campaign.render_campaign(config, output)
            normalise.assert_not_called()
            render.assert_not_called()
            self.assertFalse(output.exists())

    def test_output_overlap_and_directory_aliases_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _ = self.recipe(root)
            with self.assertRaisesRegex(ValueError, "must not contain"):
                campaign.render_campaign(config, root)
            output = root / "exports"
            output.mkdir()
            (output / "nodex").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "alias"):
                campaign.render_campaign(config, output)

    def test_fingerprint_tracks_recipe_source_icon_template_and_selection(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, data = self.recipe(root)
            loaded = campaign.load_campaign(config, ["nodex"])
            with patch.object(campaign, "_renderer_identity", return_value={"template": "v1"}):
                first = campaign.campaign_fingerprint(loaded)["fingerprint"]
                self.assertEqual(first, campaign.campaign_fingerprint(loaded)["fingerprint"])
                loaded["apps"][0]["features"][0]["source_size"] = [100, 100]
                self.assertEqual(first, campaign.campaign_fingerprint(loaded)["fingerprint"])
                (root / "source.webp").write_bytes(b"updated capture")
                source_changed = campaign.campaign_fingerprint(loaded)["fingerprint"]
                self.assertNotEqual(first, source_changed)
                (root / "icon.png").write_bytes(b"updated icon")
                icon_changed = campaign.campaign_fingerprint(loaded)["fingerprint"]
                self.assertNotEqual(source_changed, icon_changed)
                data["apps"][0]["design"]["title"] = "Updated title"
                config.write_text(json.dumps(data))
                recipe_changed = campaign.campaign_fingerprint(campaign.load_campaign(config, ["nodex"]))["fingerprint"]
                self.assertNotEqual(icon_changed, recipe_changed)
                self.assertNotEqual(recipe_changed, campaign.campaign_fingerprint(campaign.load_campaign(config))["fingerprint"])
            with patch.object(campaign, "_renderer_identity", return_value={"template": "v2"}):
                self.assertNotEqual(recipe_changed, campaign.campaign_fingerprint(campaign.load_campaign(config, ["nodex"]))["fingerprint"])

    def fake_render(self, source, output, profile, **kwargs):
        output = Path(output)
        path = output / profile / (Path(source).stem + ".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"rendered asset")
        definition = campaign.CREATIVE_PROFILES[profile]
        entry = {"profile": profile, "path": str(path), "source": str(source), "media_type": "image",
                 "locale": kwargs["locale"], "placements": list(definition.placements),
                 "width": definition.width, "height": definition.height,
                 "design": {"output": str(path), "validated": True}}
        (output / "asc_upload.json").write_text(json.dumps({"locales": {}, "creative_assets": [entry]}))
        return [path]

    def fake_normalise(self, feature, destination):
        Path(destination).write_bytes(b"normalized image")

    def test_aggregation_provenance_galleries_and_originals(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, data = self.recipe(root)
            data["apps"][0]["features"][0]["rationale"] = '<script>"why"</script>'
            config.write_text(json.dumps(data))
            output = root / "exports with spaces"
            with patch.object(campaign, "_oriented_size", return_value=(100, 100)), \
                    patch.object(campaign, "_normalise_source", side_effect=self.fake_normalise), \
                    patch.object(campaign, "process_creative_assets", side_effect=self.fake_render):
                paths = campaign.render_campaign(config, output)
            self.assertIn(output / "index.html", paths)
            app_manifest = json.loads((output / "nodex/asc_upload.json").read_text())
            self.assertEqual(len(app_manifest["creative_assets"]), 2)
            self.assertEqual(len(json.loads((output / "termex/asc_upload.json").read_text())["creative_assets"]), 3)
            entry = app_manifest["creative_assets"][0]
            self.assertEqual(entry["source"], str(root / "source.webp"))
            self.assertEqual(entry["source_provenance"]["crop"], [10, 20, 80, 60])
            self.assertEqual(entry["source_provenance"]["oriented_size"], [100, 100])
            self.assertEqual(entry["design"]["output"], entry["path"])
            self.assertTrue(Path(entry["path"]).is_file())
            gallery = (output / "index.html").read_text()
            self.assertIn("&lt;script&gt;", gallery)
            self.assertNotIn('<script>"why"', gallery)
            self.assertIn('src="nodex/hero/header/nodex-hero.png"', gallery)
            receipt = json.loads((output / "campaign_receipt.json").read_text())
            self.assertEqual(receipt["fingerprint"], entry["campaign_fingerprint"])
            self.assertEqual((root / "source.webp").read_bytes(), b"original capture")
            self.assertEqual((root / "icon.png").read_bytes(), b"original icon")

    def test_failed_render_preserves_previous_exports(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _ = self.recipe(root)
            output = root / "exports"
            output.mkdir()
            (output / "index.html").write_text("previous gallery")
            with patch.object(campaign, "_oriented_size", return_value=(100, 100)), \
                    patch.object(campaign, "_normalise_source", side_effect=self.fake_normalise), \
                    patch.object(campaign, "process_creative_assets", side_effect=RuntimeError("bad render")):
                with self.assertRaisesRegex(RuntimeError, "bad render"):
                    campaign.render_campaign(config, output)
            self.assertEqual((output / "index.html").read_text(), "previous gallery")

    def test_existing_manifest_hardlink_to_original_is_not_overwritten(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _ = self.recipe(root)
            output = root / "exports"
            (output / "nodex").mkdir(parents=True)
            (output / "nodex/asc_upload.json").hardlink_to(root / "icon.png")
            with patch.object(campaign, "_oriented_size", return_value=(100, 100)), \
                    patch.object(campaign, "_normalise_source", side_effect=self.fake_normalise), \
                    patch.object(campaign, "process_creative_assets", side_effect=self.fake_render):
                with self.assertRaisesRegex(ValueError, "overlaps an original"):
                    campaign.render_campaign(config, output, apps=["nodex"])
            self.assertEqual((root / "icon.png").read_bytes(), b"original icon")

    @unittest.skipUnless(shutil.which("magick"), "ImageMagick required")
    def test_real_crop_uses_explicit_source_pixels_and_preserves_original(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.webp"
            subprocess.run(["magick", "-size", "100x80", "xc:red", "-fill", "blue", "-draw",
                            "rectangle 20,10 59,39", str(source)], check=True, capture_output=True)
            original = source.read_bytes()
            self.assertEqual(campaign._oriented_size(source), (100, 80))
            output = root / "crop.png"
            campaign._normalise_source({"source": str(source), "crop": [20, 10, 40, 30]}, output)
            self.assertEqual(campaign._oriented_size(output), (40, 30))
            colour = subprocess.run(["magick", str(output), "-format", "%[pixel:p{20,15}]", "info:"],
                                    check=True, text=True, capture_output=True).stdout
            self.assertIn("0,0,255", colour.replace(" ", ""))
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
