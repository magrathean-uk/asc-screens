import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


def load_cli():
    path = Path(__file__).with_name("asc-gen.py")
    spec = importlib.util.spec_from_file_location("asc_gen_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AscGenCliTests(unittest.TestCase):
    def test_detected_kinds_preserves_iphone_ipad_order(self):
        cli = load_cli()
        jobs = [SimpleNamespace(device="mac"), SimpleNamespace(device="ipad"), SimpleNamespace(device="iphone")]

        self.assertEqual(cli.detected_kinds(jobs), ["iphone", "ipad", "mac"])

    def test_choose_kinds_uses_detected_when_blank(self):
        cli = load_cli()
        jobs = [SimpleNamespace(device="iphone"), SimpleNamespace(device="ipad"), SimpleNamespace(device="mac")]

        self.assertEqual(cli.choose_kinds("", jobs), ["iphone", "ipad", "mac"])

    def test_choose_kinds_accepts_both(self):
        cli = load_cli()

        self.assertEqual(cli.choose_kinds("both", []), ["iphone", "ipad", "mac"])

    def test_choose_kinds_accepts_short_aliases(self):
        cli = load_cli()

        self.assertEqual(cli.choose_kinds("i", []), ["iphone"])
        self.assertEqual(cli.choose_kinds("p", []), ["ipad"])
        self.assertEqual(cli.choose_kinds("m", []), ["mac"])
        self.assertEqual(cli.choose_kinds("b", []), ["iphone", "ipad", "mac"])

    def test_choose_kinds_accepts_latest_aliases(self):
        cli = load_cli()

        self.assertEqual(cli.choose_kinds("latest", []), ["iphone-latest", "ipad-latest", "mac-latest"])
        self.assertEqual(cli.choose_kinds("l", []), ["iphone-latest", "ipad-latest", "mac-latest"])

    def test_choose_validation_mode_accepts_check_only(self):
        cli = load_cli()

        self.assertEqual(cli.choose_validation_mode("check"), "check")
        self.assertEqual(cli.choose_validation_mode("c"), "check")
        self.assertEqual(cli.choose_validation_mode(""), "build")

    def test_choose_template_accepts_known_templates(self):
        cli = load_cli()

        self.assertEqual(cli.choose_template(""), "plain")
        self.assertEqual(cli.choose_template("top"), "title-top")
        self.assertEqual(cli.choose_template("bottom"), "title-bottom")

    def test_guided_build_with_no_output_fails_and_keeps_the_previous_manifest(self):
        import io
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        import asc_gen
        from asc_screens import ImageJob

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "asc_out"
            out.mkdir()
            stale = out / "asc_upload.json"
            stale.write_text("{}", encoding="utf-8")
            answers = iter([str(root), str(out)])
            with patch.object(asc_gen, "ask", lambda *args, **kwargs: next(answers)), \
                    patch.object(asc_gen, "prompt_mode", return_value="build"), \
                    patch.object(asc_gen, "prompt_asset", return_value="screenshots"), \
                    patch.object(asc_gen, "collect_jobs", return_value=[ImageJob(root / "a.png", "iphone")]), \
                    patch.object(asc_gen, "prompt_kinds", return_value=["iphone"]), \
                    patch.object(asc_gen, "prompt_background", return_value=["#101010", "#202020", "#303030"]), \
                    patch.object(asc_gen, "prompt_copy_file", return_value=None), \
                    patch.object(asc_gen, "prompt_template", return_value="plain"), \
                    patch.object(asc_gen, "needs_frames", return_value=False), \
                    patch.object(asc_gen, "preflight_mac_desktop"), \
                    patch.object(asc_gen, "process_kind", return_value=[]), \
                    patch("sys.stdout", new_callable=io.StringIO):
                with self.assertRaisesRegex(SystemExit, "No screenshots were produced"):
                    asc_gen.main()
            self.assertEqual(stale.read_text(encoding="utf-8"), "{}")

    def test_count_by_kind(self):
        cli = load_cli()
        jobs = [SimpleNamespace(device="iphone"), SimpleNamespace(device="ipad"), SimpleNamespace(device="iphone"), SimpleNamespace(device="mac")]

        self.assertEqual(cli.count_by_kind(jobs), {"iphone": 2, "ipad": 1, "mac": 1})


if __name__ == "__main__":
    unittest.main()
