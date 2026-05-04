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
        jobs = [SimpleNamespace(device="ipad"), SimpleNamespace(device="iphone")]

        self.assertEqual(cli.detected_kinds(jobs), ["iphone", "ipad"])

    def test_choose_kinds_uses_detected_when_blank(self):
        cli = load_cli()
        jobs = [SimpleNamespace(device="iphone"), SimpleNamespace(device="ipad")]

        self.assertEqual(cli.choose_kinds("", jobs), ["iphone", "ipad"])

    def test_choose_kinds_accepts_both(self):
        cli = load_cli()

        self.assertEqual(cli.choose_kinds("both", []), ["iphone", "ipad"])

    def test_choose_kinds_accepts_short_aliases(self):
        cli = load_cli()

        self.assertEqual(cli.choose_kinds("i", []), ["iphone"])
        self.assertEqual(cli.choose_kinds("p", []), ["ipad"])
        self.assertEqual(cli.choose_kinds("b", []), ["iphone", "ipad"])

    def test_count_by_kind(self):
        cli = load_cli()
        jobs = [SimpleNamespace(device="iphone"), SimpleNamespace(device="ipad"), SimpleNamespace(device="iphone")]

        self.assertEqual(cli.count_by_kind(jobs), {"iphone": 2, "ipad": 1})


if __name__ == "__main__":
    unittest.main()
