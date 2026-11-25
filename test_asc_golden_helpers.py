"""Unit tests for the golden check's own plumbing (not the rendering). They run everywhere:
no ImageMagick, Swift or Apple Frames is needed, and ASC_GOLDEN does not have to be set."""

import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import asc_screens
import test_asc_golden as golden
from asc_screens import ValidationReport

CASE = {"name": "iphone-caption", "device": "iphone", "size": [1320, 2868], "output": "en-GB/iphone/Dashboard.png"}


def check_case_harness(work, validator, update=False):
    """GoldenRenderTests.check_case with the render, ImageMagick and reference folder replaced."""
    test = golden.GoldenRenderTests("check_case")
    test.work = Path(work)
    output = Path(work) / "out.png"
    output.touch()
    test.render = lambda case: output
    reference_dir = Path(work) / "references"
    reference_dir.mkdir()
    magick = MagicMock(side_effect=lambda *args, **kwargs: Path(str(args[-1]).removeprefix("PNG24:")).touch())
    patches = [
        patch.object(golden, "validate_screenshot_file", validator),
        patch.object(golden, "image_size", return_value=(1320, 2868)),
        patch.object(golden, "magick", magick),
        patch.object(golden, "REFERENCE_DIR", reference_dir),
        patch.object(golden, "UPDATE", update),
    ]
    return test, patches, magick, reference_dir


class GoldenOutputValidationTests(unittest.TestCase):
    def run_check(self, report, update):
        validator = MagicMock(return_value=report)
        with tempfile.TemporaryDirectory() as work:
            test, patches, magick, reference_dir = check_case_harness(work, validator, update)
            for item in patches:
                item.start()
                self.addCleanup(item.stop)
            with self.assertRaises(AssertionError) as raised:
                test.check_case(CASE)
            wrote_reference = any(reference_dir.iterdir())
        validator.assert_called_once()
        self.assertEqual(validator.call_args.args[1], "iphone")
        return str(raised.exception), magick, wrote_reference

    def transparent_report(self):
        return ValidationReport(path=Path("out.png"), ok=False, detected_size=(1320, 2868),
                                problems=("transparency is not allowed for App Store screenshots",))

    def test_transparent_output_fails_before_it_is_normalised(self):
        message, magick, _ = self.run_check(self.transparent_report(), update=False)
        self.assertIn("transparency", message)
        magick.assert_not_called()  # alpha is stripped by the first magick call; validation comes before it

    def test_transparent_output_cannot_become_a_reference_in_update_mode(self):
        message, magick, wrote_reference = self.run_check(self.transparent_report(), update=True)
        self.assertIn("transparency", message)
        self.assertFalse(wrote_reference)
        magick.assert_not_called()


class BoundedProcessTests(unittest.TestCase):
    def test_identify_calls_have_a_deadline(self):
        for function in (asc_screens.image_size, asc_screens.has_alpha):
            with self.subTest(function=function.__name__), patch("asc_screens.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, stdout="10 20" if function is asc_screens.image_size else "srgba", stderr="")
                function(Path("x.png"))
            timeout = run.call_args.kwargs.get("timeout")
            self.assertIsInstance(timeout, (int, float))
            self.assertGreater(timeout, 0)

    def test_xcode_probe_has_a_deadline_and_reports_a_timeout(self):
        with patch.object(golden, "run_bounded", side_effect=subprocess.TimeoutExpired(["xcode-select"], 1)) as bounded:
            reason = golden.probe_xcode()
        self.assertIn("timed out", reason)
        self.assertEqual(bounded.call_args.args[1], golden.TOOL_TIMEOUT)

    def test_xcode_probe_reports_missing_tools(self):
        with patch.object(golden, "run_bounded", return_value=subprocess.CompletedProcess([], 2, "", "")):
            self.assertIn("xcode-select --install", golden.probe_xcode())
        with patch.object(golden, "run_bounded", return_value=subprocess.CompletedProcess([], 0, "/Library/Developer\n", "")):
            self.assertIsNone(golden.probe_xcode())

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX only")
    def test_timeout_recovery_is_bounded_when_the_group_kill_fails(self):
        # The grandchild keeps the pipes open for 5 s; without a bound on the drain,
        # run_bounded would sit in communicate() until it exits.
        command = ["sh", "-c", "sleep 5 & sleep 5"]
        with patch.object(golden, "KILL_GRACE", 1), patch("test_asc_golden.os.killpg", side_effect=PermissionError):
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                golden.run_bounded(command, 2)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 4.9)  # 2 s timeout + 1 s grace; unbounded would wait for the 5 s grandchild

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX only")
    def test_timeout_kills_the_whole_group_and_keeps_partial_output(self):
        command = ["sh", "-c", "echo started; sleep 30 & sleep 30"]
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired) as raised:
            golden.run_bounded(command, 3)
        self.assertLess(time.monotonic() - started, 15)
        self.assertIn("started", raised.exception.output or "")

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX only")
    def test_an_interrupt_kills_the_child_instead_of_leaking_it(self):
        started = []

        class Interrupted(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                started.append(self)

            def communicate(self, *args, **kwargs):
                raise KeyboardInterrupt

        with patch.object(golden.subprocess, "Popen", Interrupted):
            with self.assertRaises(KeyboardInterrupt):
                golden.run_bounded(["sleep", "20"], 30)
        try:
            self.assertIsNotNone(started[0].wait(timeout=5), "child survived the interrupt")
        finally:
            if started[0].poll() is None:
                started[0].kill()

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX only")
    def test_normal_run_returns_output_and_status(self):
        result = golden.run_bounded(["sh", "-c", "echo out; echo err >&2; exit 3"], 10)
        self.assertEqual((result.returncode, result.stdout.strip(), result.stderr.strip()), (3, "out", "err"))


class FailureDirTests(unittest.TestCase):
    def failure_dir(self, value):
        env = {"ASC_GOLDEN_OUT": value} if value is not None else {}
        with patch.dict(os.environ, env, clear=False):
            if value is None:
                os.environ.pop("ASC_GOLDEN_OUT", None)
            with patch("sys.stderr", new_callable=io.StringIO):
                return golden.failure_dir()

    def test_checkout_local_destinations_are_redirected_to_the_temp_directory(self):
        default = Path(tempfile.gettempdir()) / "asc-screens-golden"
        with tempfile.TemporaryDirectory() as elsewhere:
            previous = Path.cwd()
            os.chdir(golden.ROOT)
            self.addCleanup(os.chdir, previous)
            for value in (".", "golden-out", str(golden.ROOT), str(golden.ROOT / "tests" / "golden" / "failures"), "tests/golden"):
                with self.subTest(value=value):
                    self.assertEqual(self.failure_dir(value), default)
            os.chdir(elsewhere)
            self.assertEqual(self.failure_dir("failures"), Path(elsewhere).resolve() / "failures")

    def test_external_and_default_destinations_are_kept(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(self.failure_dir(elsewhere), Path(elsewhere).resolve())
        self.assertEqual(self.failure_dir(None), Path(tempfile.gettempdir()) / "asc-screens-golden")


if __name__ == "__main__":
    unittest.main()
