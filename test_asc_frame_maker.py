import unittest
import json
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from argparse import Namespace
from unittest.mock import patch

from asc_screens import (
    APP_STORE_IPHONE_TARGETS,
    APP_STORE_MAC_TARGETS,
    app_preview_output_path,
    background_command,
    build_app_preview_command,
    classify_device_from_size,
    collect_jobs,
    derive_background_palette,
    expand_export_targets,
    fit_inside,
    expand_background_palette,
    list_pngs,
    load_config,
    load_localizations,
    composite,
    title_from_source,
    overlay_text_command,
    output_path_for_source,
    resolve_background_palette,
    resolve_configured_args,
    resolve_config_paths,
    frame_inputs,
    ImageJob,
    process_app_preview,
    process_kind,
    process_mac,
    target_for_kind,
    validate_output_dir,
    validate_screenshot_file,
    write_contact_sheet,
    write_review_manifest,
    write_upload_manifest,
)


class AscFrameMakerTests(unittest.TestCase):
    def test_target_for_kind(self):
        self.assertEqual(target_for_kind("iphone"), (1320, 2868))
        self.assertEqual(target_for_kind("ipad"), (2064, 2752))
        self.assertEqual(target_for_kind("mac"), (2880, 1800))

    def test_iphone_target_uses_largest_app_store_size(self):
        portrait_targets = [size for size in APP_STORE_IPHONE_TARGETS if size[1] > size[0]]
        largest = max(portrait_targets, key=lambda size: size[0] * size[1])
        self.assertEqual(target_for_kind("iphone"), largest)

    def test_mac_target_uses_largest_app_store_size(self):
        largest = max(APP_STORE_MAC_TARGETS, key=lambda size: size[0] * size[1])
        self.assertEqual(target_for_kind("mac"), largest)

    def test_fit_inside_preserves_aspect_ratio(self):
        self.assertEqual(fit_inside((1470, 3000), (1110, 2530)), (1110, 2265))
        self.assertEqual(fit_inside((2300, 3000), (1840, 2400)), (1840, 2400))

    def test_fit_inside_never_upscales(self):
        self.assertEqual(fit_inside((100, 200), (1000, 1000)), (100, 200))

    def test_output_path_for_source_is_png(self):
        output = output_path_for_source(Path("asc_out/iphone"), Path("01-home.jpg"))

        self.assertEqual(output, Path("asc_out/iphone/01-home.png"))

    def test_title_from_source_strips_ipad_suffix(self):
        self.assertEqual(title_from_source(Path("01-home-ipad.png")), "01-home")
        self.assertEqual(title_from_source(Path("01-home.png")), "01-home")

    def test_classify_device_from_size(self):
        self.assertEqual(classify_device_from_size(1284, 2778), "iphone")
        self.assertEqual(classify_device_from_size(1320, 2868), "iphone")
        self.assertEqual(classify_device_from_size(2064, 2752), "ipad")
        self.assertEqual(classify_device_from_size(2880, 1800), "mac")
        self.assertEqual(classify_device_from_size(3456, 2234), "mac")

    def test_validate_png_reports_wrong_size(self):
        report = validate_screenshot_file(Path("bad.png"), "iphone", size_reader=lambda _: (1080, 1920))

        self.assertFalse(report.ok)
        self.assertEqual(report.detected_size, (1080, 1920))
        self.assertTrue(any("size" in problem.lower() for problem in report.problems))

    def test_validate_png_rejects_alpha_channel(self):
        report = validate_screenshot_file(
            Path("bad.png"),
            "iphone",
            size_reader=lambda _: (1320, 2868),
            alpha_reader=lambda _: True,
        )

        self.assertFalse(report.ok)
        self.assertTrue(any("transparency" in problem.lower() for problem in report.problems))

    def test_validate_directory_counts_failures(self):
        reports = {
            Path("ok.png"): validate_screenshot_file(Path("ok.png"), "iphone", size_reader=lambda _: (1320, 2868), alpha_reader=lambda _: False),
            Path("bad.png"): validate_screenshot_file(Path("bad.png"), "iphone", size_reader=lambda _: (1080, 1920), alpha_reader=lambda _: False),
        }

        summary = validate_output_dir(
            Path("asc_out/iphone"),
            kind="iphone",
            files=[Path("ok.png"), Path("bad.png")],
            validator=lambda path, kind: reports[path],
        )

        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.passed, 1)
        self.assertEqual(summary.failed, 1)

    def test_expand_kind_selection_for_iphone_latest(self):
        self.assertEqual(expand_export_targets("iphone-latest"), [("iphone", (1320, 2868))])

    def test_expand_kind_selection_for_all_latest(self):
        self.assertEqual(
            expand_export_targets("all-latest"),
            [("iphone", (1320, 2868)), ("ipad", (2064, 2752)), ("mac", (2880, 1800))],
        )

    def test_expand_kind_selection_for_mac(self):
        self.assertEqual(expand_export_targets("mac"), [("mac", (2880, 1800))])

    def test_load_config_reads_json_file(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "asc-screens.json"
            config_path.write_text(json.dumps({"source": "./shots", "output_root": "build/asc"}), encoding="utf-8")

            config = load_config(config_path)

        self.assertEqual(config["source"], "./shots")
        self.assertEqual(config["output_root"], "build/asc")

    def test_resolve_configured_args_uses_config_for_defaulted_values(self):
        args = Namespace(
            source=".",
            output_root="asc_out",
            frames_bin="/Users/test/.local/bin/frames",
            background=None,
            theme="teslatlas",
            frame_color="Silver",
            kind="all",
            check=False,
            validate=True,
            config="asc-screens.json",
        )
        defaults = {
            "source": ".",
            "output_root": "asc_out",
            "frames_bin": "/Users/test/.local/bin/frames",
            "background": None,
            "theme": "teslatlas",
            "frame_color": "Silver",
            "kind": "all",
            "check": False,
            "validate": True,
            "config": None,
        }

        resolved = resolve_configured_args(
            args,
            {"source": "./shots", "output_root": "build/asc", "kind": "iphone-latest", "check": True},
            defaults,
        )

        self.assertEqual(resolved.source, "./shots")
        self.assertEqual(resolved.output_root, "build/asc")
        self.assertEqual(resolved.kind, "iphone-latest")
        self.assertTrue(resolved.check)

    def test_resolve_config_paths_uses_config_directory(self):
        args = Namespace(
            source="shots",
            output_root="build/asc",
            copy_file="copy.json",
        )

        resolved = resolve_config_paths(args, Path("/tmp/spec/asc-screens.json"))

        self.assertEqual(resolved.source, Path("/tmp/spec/shots").resolve())
        self.assertEqual(resolved.output_root, Path("/tmp/spec/build/asc").resolve())
        self.assertEqual(resolved.copy_file, Path("/tmp/spec/copy.json").resolve())

    def test_write_review_manifest_lists_outputs_in_order(self):
        with TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            outputs = [
                output_root / "iphone" / "02-home.png",
                output_root / "iphone" / "01-login.png",
                output_root / "ipad" / "03-settings.png",
            ]
            for output in outputs:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.touch()

            manifest_path = write_review_manifest(output_root, outputs)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["items"][0]["slot"], 1)
        self.assertEqual(manifest["items"][0]["family"], "iphone")
        self.assertEqual(manifest["items"][0]["filename"], "01-login.png")
        self.assertEqual(manifest["items"][2]["family"], "ipad")

    def test_write_review_manifest_skips_when_no_outputs(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(write_review_manifest(Path(tmp), []))

    def test_write_contact_sheet_creates_html_preview(self):
        with TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            outputs = [
                output_root / "en-GB" / "iphone" / "01-login.png",
                output_root / "en-GB" / "iphone" / "02-home.png",
            ]
            for output in outputs:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.touch()

            contact_sheet = write_contact_sheet(output_root, outputs)
            html = contact_sheet.read_text(encoding="utf-8")

        self.assertIn("01-login.png", html)
        self.assertIn("en-GB", html)
        self.assertIn("iphone", html)

    def test_load_localizations_reads_locale_copy(self):
        with TemporaryDirectory() as tmp:
            copy_path = Path(tmp) / "copy.json"
            copy_path.write_text(
                json.dumps(
                    {
                        "en-GB": {"title": "Fast EV planning", "subtitle": "Route, charge, arrive"},
                        "de-DE": {"title": "Schnelle EV Planung", "subtitle": "Route, laden, ankommen"},
                    }
                ),
                encoding="utf-8",
            )

            localizations = load_localizations(copy_path)

        self.assertEqual(localizations["en-GB"]["title"], "Fast EV planning")
        self.assertEqual(localizations["de-DE"]["subtitle"], "Route, laden, ankommen")

    def test_overlay_text_command_uses_bottom_template(self):
        command = overlay_text_command(1320, 2868, "title-bottom", {"title": "Fast EV planning", "subtitle": "Route, charge, arrive"})

        self.assertIn("-gravity", command)
        self.assertIn("south", command)
        self.assertTrue(any("Fast EV planning" in part for part in command))
        self.assertTrue(any("Route, charge, arrive" in part for part in command))

    @patch("asc_screens.run")
    @patch("asc_screens.overlay_text_command", side_effect=lambda width, height, template, copy: [copy["title"]])
    @patch("asc_screens.background_command", return_value=[])
    @patch("asc_screens.image_size", return_value=(100, 200))
    @patch("asc_screens.fit_inside", return_value=(100, 200))
    def test_composite_uses_filename_title_when_copy_missing(self, _fit_inside, _image_size, _background_command, _overlay_text_command, run_mock):
        composite("iphone", Path("launch-screen-ipad.png"), Path("frame.png"), Path("out"), ["#000000", "#111111", "#222222"], template="title-top")

        command = run_mock.call_args.args[0]
        self.assertIn("launch-screen", command)

    def test_write_upload_manifest_groups_by_locale_and_family(self):
        with TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            outputs = [
                output_root / "en-GB" / "iphone" / "01-login.png",
                output_root / "en-GB" / "iphone" / "02-home.png",
                output_root / "de-DE" / "ipad" / "01-login.png",
            ]
            for output in outputs:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.touch()

            manifest_path = write_upload_manifest(output_root, outputs)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["locales"]["en-GB"]["iphone"][0]["slot"], 1)
        self.assertEqual(manifest["locales"]["en-GB"]["iphone"][1]["filename"], "02-home.png")
        self.assertEqual(manifest["locales"]["de-DE"]["ipad"][0]["filename"], "01-login.png")

    def test_teslatlas_background_is_imagemagick_command(self):
        command = background_command(1284, 2778, resolve_background_palette(theme="teslatlas"))
        self.assertEqual(command[:3], ["-size", "1284x2778", "xc:#060914"])
        self.assertIn("-sparse-color", command)

    def test_single_color_background_becomes_three_colors(self):
        palette = resolve_background_palette("#FF8800")
        self.assertEqual(len(palette), 3)
        self.assertTrue(all(color.startswith("#") and len(color) == 7 for color in palette))

    def test_two_color_background_becomes_three_colors(self):
        palette = resolve_background_palette("#FF8800,#0088FF")
        self.assertEqual(len(palette), 3)
        self.assertEqual(palette[0], "#FF8800")
        self.assertEqual(palette[2], "#0088FF")

    def test_expand_background_palette_handles_two_colors(self):
        self.assertEqual(expand_background_palette(["#111111", "#999999"]), ["#111111", "#555555", "#999999"])

    def test_background_derivation_changes_hue(self):
        palette = derive_background_palette("#FF8800")
        self.assertEqual(len(palette), 3)
        self.assertNotEqual(palette[0], palette[1])

    def test_list_pngs_accepts_uppercase_extension(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            upper = root / "A.PNG"
            lower = root / "b.png"
            other = root / "notes.txt"
            upper.touch()
            lower.touch()
            other.touch()

            self.assertEqual(list_pngs(root), [upper, lower])

    def test_list_pngs_accepts_common_screenshot_extensions(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "shot.JPG"
            jpeg = root / "shot.jpeg"
            heic = root / "shot.HEIC"
            text = root / "notes.txt"
            jpg.touch()
            jpeg.touch()
            heic.touch()
            text.touch()

            self.assertEqual(list_pngs(root), [heic, jpg, jpeg])

    def test_collect_jobs_finds_device_folders_in_subdirs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            iphone = root / "set-a" / "iphone"
            ipad = root / "set-b" / "nested" / "ipad"
            mac = root / "set-c" / "mac"
            iphone.mkdir(parents=True)
            ipad.mkdir(parents=True)
            mac.mkdir(parents=True)
            phone_shot = iphone / "phone.PNG"
            pad_shot = ipad / "pad.png"
            mac_shot = mac / "mac.png"
            phone_shot.touch()
            pad_shot.touch()
            mac_shot.touch()

            jobs = collect_jobs(root)

            self.assertEqual([(job.source, job.device) for job in jobs], [(phone_shot, "iphone"), (pad_shot, "ipad"), (mac_shot, "mac")])

    def test_collect_jobs_ignores_generated_output_folders(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "raw" / "iphone"
            output_dir = root / "asc_out" / "iphone"
            framed_dir = root / "asc_out" / "_framed" / "iphone"
            source_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            framed_dir.mkdir(parents=True)
            source = source_dir / "source.png"
            generated = output_dir / "generated.png"
            framed = framed_dir / "source_framed.png"
            source.touch()
            generated.touch()
            framed.touch()

            jobs = collect_jobs(root)

            self.assertEqual([(job.source, job.device) for job in jobs], [(source, "iphone")])

    def test_frame_inputs_skips_files_that_fail_to_frame(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "good.png"
            bad = root / "bad.png"
            out = root / "framed"
            good.touch()
            bad.touch()

            def fake_run(cmd):
                source = Path(cmd[-1])
                if source == bad:
                    raise CalledProcessError(1, cmd, stderr="bad image")
                (out / f"{source.stem}_framed.png").touch()

            jobs = [ImageJob(good, "iphone"), ImageJob(bad, "iphone")]
            with patch("asc_screens.run", side_effect=fake_run):
                framed = frame_inputs("iphone", jobs, out, Path("frames"), "Silver")

            self.assertEqual(framed, [(good, out / "good_framed.png")])

    def test_process_kind_skips_composite_failures(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "good.png"
            bad = root / "bad.png"
            good_frame = root / "good_framed.png"
            bad_frame = root / "bad_framed.png"
            output = root / "out" / "iphone" / "good.png"
            args = Namespace(output_root=root / "out", frames_bin="frames", frame_color="Silver", validate=False)
            jobs = [ImageJob(good, "iphone"), ImageJob(bad, "iphone")]

            def fake_composite(kind, source, framed, output_dir, background_colors):
                if source == bad:
                    raise CalledProcessError(1, ["magick"], stderr="bad composite")
                return output

            with patch("asc_screens.frame_inputs", return_value=[(good, good_frame), (bad, bad_frame)]):
                with patch("asc_screens.composite", side_effect=fake_composite):
                    outputs = process_kind(args, jobs, "iphone", ["#000000", "#111111", "#222222"])

            self.assertEqual(outputs, [output])

    @patch("asc_screens.run")
    def test_process_mac_scales_exact_without_framing_or_text(self, run_mock):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "desktop.png"
            source.touch()
            args = Namespace(output_root=root / "out", validate=False)

            outputs = process_mac(args, [ImageJob(source, "mac")], target_size=(2880, 1800))

        self.assertEqual(len(outputs), 1)
        command = run_mock.call_args.args[0]
        self.assertIn("-resize", command)
        self.assertIn("2880x1800!", command)
        self.assertNotIn("-composite", command)
        self.assertNotIn("caption:", " ".join(command))

    def test_app_preview_command_uses_app_store_safe_video_settings(self):
        command = build_app_preview_command(Path("in.mp4"), Path("out.mp4"), size=(886, 1920), fps=30, max_duration=30)

        self.assertIn("scale=886:1920:flags=lanczos,fps=30,setsar=1", command)
        self.assertIn("-level", command)
        self.assertIn("4.0", command)
        self.assertIn("-t", command)
        self.assertIn("30", command)
        self.assertIn("anullsrc=channel_layout=stereo:sample_rate=44100", command)
        self.assertIn("-c:a", command)
        self.assertIn("aac", command)
        self.assertIn("256k", command)

    def test_app_preview_output_path_names_constraints(self):
        output = app_preview_output_path(Path("asc_out"), Path("Screen Recording.mp4"), (886, 1920), 30)

        self.assertEqual(output, Path("asc_out/video/Screen Recording_886x1920_30fps_30s_level40_silent-aac.mp4"))

    @patch("asc_screens.run")
    def test_process_app_preview_runs_ffmpeg_command(self, run_mock):
        output = process_app_preview(Path("source.mp4"), Path("asc_out"), size=(886, 1920), fps=30, max_duration=30)

        self.assertEqual(output, Path("asc_out/video/source_886x1920_30fps_30s_level40_silent-aac.mp4"))
        self.assertEqual(run_mock.call_args.args[0][0], "ffmpeg")


if __name__ == "__main__":
    unittest.main()
