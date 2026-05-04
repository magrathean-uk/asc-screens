import unittest
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from argparse import Namespace
from unittest.mock import patch

from asc_screens import (
    APP_STORE_IPHONE_TARGETS,
    background_command,
    classify_device_from_size,
    collect_jobs,
    derive_background_palette,
    fit_inside,
    expand_background_palette,
    list_pngs,
    resolve_background_palette,
    frame_inputs,
    ImageJob,
    process_kind,
    target_for_kind,
)


class AscFrameMakerTests(unittest.TestCase):
    def test_target_for_kind(self):
        self.assertEqual(target_for_kind("iphone"), (1284, 2778))
        self.assertEqual(target_for_kind("ipad"), (2064, 2752))

    def test_iphone_target_uses_largest_app_store_size(self):
        portrait_targets = [size for size in APP_STORE_IPHONE_TARGETS if size[1] > size[0]]
        largest = max(portrait_targets, key=lambda size: size[0] * size[1])
        self.assertEqual(target_for_kind("iphone"), largest)

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
            iphone.mkdir(parents=True)
            ipad.mkdir(parents=True)
            phone_shot = iphone / "phone.PNG"
            pad_shot = ipad / "pad.png"
            phone_shot.touch()
            pad_shot.touch()

            jobs = collect_jobs(root)

            self.assertEqual([(job.source, job.device) for job in jobs], [(phone_shot, "iphone"), (pad_shot, "ipad")])

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


if __name__ == "__main__":
    unittest.main()
