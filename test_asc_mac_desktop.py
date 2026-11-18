import datetime
import json
import plistlib
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import asc_mac_desktop as mac
from asc_screens import ImageJob, process_mac


def make_bundle(root, name, display=None):
    bundle = root / f"{name}.app"
    (bundle / "Contents").mkdir(parents=True)
    info = {"CFBundleName": name}
    if display:
        info["CFBundleDisplayName"] = display
    with (bundle / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)
    return bundle


def options(**overrides):
    values = {"app_name": "Tescam", "app_icon": None, "menus": mac.DEFAULT_MENUS, "clock": "Wed 18 Nov 9:41",
              "wallpaper": None, "dock_apps": ()}
    values.update(overrides)
    return mac.MacDesktopOptions(**values)


class MacOptionsTests(unittest.TestCase):
    def test_bundle_supplies_menu_bar_name(self):
        with TemporaryDirectory() as tmp:
            bundle = make_bundle(Path(tmp), "Tescam", display="Tescam Pro")
            resolved = mac.resolve_options(Namespace(mac_app=str(bundle)))
        self.assertEqual(resolved.app_name, "Tescam Pro")
        self.assertEqual(resolved.menus, mac.DEFAULT_MENUS)

    def test_explicit_name_and_lists_override_defaults(self):
        resolved = mac.resolve_options(Namespace(mac_app_name="WGEX", mac_menus="File, Tunnel ,Help",
                                                 mac_dock=["/System/Library/CoreServices/Finder.app"], mac_clock="Mon 9:41"))
        self.assertEqual(resolved.app_name, "WGEX")
        self.assertEqual(resolved.menus, ("File", "Tunnel", "Help"))
        self.assertEqual(resolved.dock_apps, ("/System/Library/CoreServices/Finder.app",))
        self.assertEqual(resolved.clock, "Mon 9:41")

    def test_name_is_required_without_a_bundle(self):
        with TemporaryDirectory() as tmp:
            icon = Path(tmp) / "icon.png"
            icon.touch()
            with self.assertRaisesRegex(ValueError, "--mac-app-name"):
                mac.resolve_options(Namespace(mac_app=str(icon)))
        with self.assertRaisesRegex(ValueError, "not found"):
            mac.resolve_options(Namespace(mac_app="/missing/Nothing.app"))

    def test_explicit_dock_entries_must_exist(self):
        with self.assertRaisesRegex(ValueError, "Dock entries not found: /missing/B.app"):
            mac.resolve_options(Namespace(mac_app_name="Tescam", mac_dock="/missing/B.app"))

    def test_config_dock_paths_resolve_beside_the_config(self):
        from asc_screens import resolve_config_paths

        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "asc-screens.json"
            resolved = resolve_config_paths(Namespace(mac_dock=["icons/a.png", "/Applications/B.app"]), config)
        self.assertEqual(resolved.mac_dock, [str(Path(tmp).resolve() / "icons/a.png"), "/Applications/B.app"])

    def test_default_clock_uses_the_date_at_941(self):
        self.assertEqual(mac.default_clock(datetime.date(2026, 11, 18)), "Wed 18 Nov 9:41")


class DockTests(unittest.TestCase):
    def test_dock_skips_missing_apps_and_ends_with_running_app_then_trash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            finder = make_bundle(root, "Finder")
            icon = root / "icon.png"
            icon.touch()
            entries = mac.dock_entries(options(app_icon=icon, dock_apps=(str(finder), str(root / "Gone.app"))),
                                       opaque_corner=lambda path: True)
        self.assertEqual([entry["kind"] for entry in entries], ["app", "image", "trash"])
        self.assertTrue(entries[0]["running"])
        self.assertEqual(entries[1], {"source": str(icon), "kind": "image", "mask": True, "running": True})

    def test_app_already_in_dock_is_marked_running_not_repeated(self):
        with TemporaryDirectory() as tmp:
            bundle = make_bundle(Path(tmp), "Tescam")
            entries = mac.dock_entries(options(app_icon=bundle, dock_apps=(str(bundle),)))
        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0]["running"])


class LayoutTests(unittest.TestCase):
    def entries(self, count=9):
        apps = [{"kind": "app"}] * (count - 1)
        return [*apps, {"kind": "trash"}]

    def test_layout_keeps_menu_bar_dock_and_window_area_apart(self):
        layout = mac.desktop_layout((2880, 1800), self.entries())
        dock_x, dock_y, dock_w, dock_h = layout.dock_rect
        area_x, area_y, area_w, area_h = layout.window_area
        self.assertEqual(layout.menubar_height, 48)
        self.assertAlmostEqual(dock_x + dock_w / 2, 1440)
        self.assertLess(dock_y + dock_h, 1800)
        self.assertGreater(area_y, layout.menubar_height)
        self.assertLess(area_y + area_h, dock_y)
        self.assertEqual(len(layout.tiles), 9)
        self.assertEqual(len(layout.separators), 1)
        self.assertLess(layout.separators[0][0], layout.tiles[-1][0])
        self.assertGreater(layout.separators[0][0], layout.tiles[-2][0] + layout.tiles[-2][2])

    def test_dock_wider_than_the_screen_is_refused(self):
        with self.assertRaisesRegex(ValueError, "too many apps"):
            mac.desktop_layout((1280, 800), self.entries(30))

    def test_window_keeps_natural_size_when_it_fits(self):
        layout = mac.desktop_layout((2880, 1800), self.entries())
        x, y, w, h = mac.window_rect(layout, (2000, 1250))
        self.assertEqual((w, h), (2000, 1250))
        self.assertEqual(x, 440)

    def test_full_screen_capture_shrinks_into_the_free_area(self):
        for size in ((2880, 1800), (1280, 800)):
            layout = mac.desktop_layout(size, self.entries())
            x, y, w, h = mac.window_rect(layout, (2880, 1800))
            area_x, area_y, area_w, area_h = layout.window_area
            self.assertLessEqual(h, round(area_h))
            self.assertGreaterEqual(y, area_y - 1)
            self.assertAlmostEqual(w / h, 1.6, places=2)
            self.assertLess(w, size[0])


class RenderTests(unittest.TestCase):
    def test_render_writes_script_and_spec_then_runs_swift(self):
        calls = []
        layout = mac.desktop_layout((2880, 1800), [{"kind": "app"}, {"kind": "trash"}])
        entries = [{"source": "/F.app", "kind": "app", "mask": False, "running": True},
                   {"source": "trash", "kind": "trash", "mask": False, "running": False}]
        spec = mac.build_spec((2880, 1800), layout, entries, options(), "wall.png", True, True,
                              [("in.png", (1, 2, 3, 4), True, "out.png")])
        with TemporaryDirectory() as tmp:
            spec_path = mac.render(spec, tmp, swift_bin="swift", runner=lambda cmd, check: calls.append(cmd))
            written = json.loads(spec_path.read_text())
            script = Path(tmp) / "asc_mac_desktop.swift"
            self.assertEqual(script.read_text(), mac.SWIFT_RENDERER)
        self.assertEqual(calls, [["swift", str(script), str(spec_path)]])
        self.assertEqual(written["menubar"]["app_name"], "Tescam")
        self.assertEqual(written["dock"]["tiles"][0]["rect"], list(layout.tiles[0]))
        self.assertEqual(written["jobs"], [{"window": "in.png", "rect": [1, 2, 3, 4], "radius": 32.0,
                                            "decorate": True, "output": "out.png"}])


class ProcessMacDesktopTests(unittest.TestCase):
    @patch("asc_screens.region_brightness", return_value=0.2)
    @patch("asc_screens.corner_alpha", return_value=1.0)
    @patch("asc_screens.image_size", return_value=(2880, 1800))
    @patch("asc_screens.shutil.which", return_value="/usr/bin/swift")
    @patch("asc_screens.mac_desktop.render")
    @patch("asc_screens.run")
    def test_desktop_style_renders_one_spec_and_flattens_each_output(self, run_mock, render_mock, *_mocks):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [root / "01.png", root / "02.png"]
            args = Namespace(output_root=root / "out", validate=False, mac_app_name="Tescam", mac_dock=[],
                             mac_style="desktop")
            outputs = process_mac(args, [ImageJob(path, "mac") for path in sources], target_size=(2880, 1800),
                                  background_colors=["#000000", "#111111", "#222222"])

        self.assertEqual([path.name for path in outputs], ["01.png", "02.png"])
        spec = render_mock.call_args.args[0]
        self.assertEqual([job["decorate"] for job in spec["jobs"]], [True, True])
        self.assertTrue(spec["menubar"]["dark"])
        wallpaper_command, *flatten = [call.args[0] for call in run_mock.call_args_list]
        self.assertIn("-sparse-color", wallpaper_command)
        self.assertEqual(len(flatten), 2)
        self.assertTrue(flatten[0][-1].startswith("PNG24:"))

    @patch("asc_screens.composite", side_effect=lambda kind, source, framed, output_dir, *a, **k: output_dir / source.name)
    @patch("asc_screens.region_brightness", return_value=0.2)
    @patch("asc_screens.corner_alpha", return_value=1.0)
    @patch("asc_screens.image_size", return_value=(2880, 1800))
    @patch("asc_screens.shutil.which", return_value="/usr/bin/swift")
    @patch("asc_screens.mac_desktop.render")
    @patch("asc_screens.run")
    def test_framed_style_renders_macbook_screen_then_frames_and_composites(self, run_mock, render_mock, _which,
                                                                            _size, _alpha, _bright, composite_mock):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            framed = root / "out" / "_framed" / "mac" / "01_framed.png"
            framed.parent.mkdir(parents=True)
            framed.touch()
            args = Namespace(output_root=root / "out", validate=False, mac_app_name="Tescam", mac_dock=[],
                             frames_bin="frames", frame_color="Silver")
            outputs = process_mac(args, [ImageJob(root / "01.png", "mac")], target_size=(2880, 1800),
                                  background_colors=["#000000", "#111111", "#222222"])

        spec = render_mock.call_args.args[0]
        self.assertEqual((spec["width"], spec["height"]), mac.MACBOOK_SCREEN)
        self.assertEqual(spec["menubar"]["height"], 74)
        frames_command = run_mock.call_args_list[-1].args[0]
        self.assertEqual(frames_command[:2], ["frames", "frame"])
        self.assertIn("Silver", frames_command)
        self.assertEqual(composite_mock.call_args.args[:3], ("mac", root / "01.png", framed))
        self.assertEqual(composite_mock.call_args.kwargs["target_size"], (2880, 1800))
        self.assertEqual([path.name for path in outputs], ["01.png"])

    @patch("asc_screens.shutil.which", return_value=None)
    def test_desktop_style_explains_missing_swift(self, _which):
        args = Namespace(output_root="out", validate=False, mac_app_name="Tescam")
        with self.assertRaisesRegex(SystemExit, "xcode-select"):
            process_mac(args, [ImageJob(Path("01.png"), "mac")], target_size=(2880, 1800))


if __name__ == "__main__":
    unittest.main()
