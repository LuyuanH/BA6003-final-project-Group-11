"""Do a startup test with the Streamlit entry point and component imports."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from amlens.services.case_service import ReplayDataset
from tests.unit.test_replay import fixture_records

APP = Path(__file__).resolve().parents[2] / "src/amlens/app.py"
ROOT = APP.parents[2]


class AppStartupTests(unittest.TestCase):
    def test_cloud_checkout_starts_without_local_data_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            shutil.copy(ROOT / "streamlit_app.py", checkout)
            shutil.copytree(
                ROOT / "src/amlens",
                checkout / "src/amlens",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            shutil.copytree(ROOT / "deployment", checkout / "deployment")
            # Clear already imported source modules in the isolated subprocess below.
            import subprocess
            import sys

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from streamlit.testing.v1 import AppTest; "
                    "app = AppTest.from_file('streamlit_app.py').run(timeout=30); "
                    "assert not list(app.exception), list(app.exception); "
                    "assert not list(app.error), list(app.error); "
                    "assert app.session_state['amlens_observatory__dataset']",
                ],
                cwd=checkout,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((checkout / "data").exists())

    def test_cloud_missing_snapshot_shows_export_instructions(self):
        with patch("amlens.services.snapshot_service.load_replay_snapshot", side_effect=ValueError):
            app = AppTest.from_file(ROOT / "streamlit_app.py").run(timeout=10)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.error), 1)
        self.assertIn("export_replay.py", app.code[0].value)

    def test_replacing_results_resets_clock_reviews_and_component_identity(self):
        original = ReplayDataset(fixture_records())
        records = fixture_records()
        records["evidence"][0]["case_id"] = "replacement"
        replacement = ReplayDataset(records)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "present.sqlite"
            database.touch()
            with (
                patch("amlens.config.OBSERVATION_DB", database),
                patch("amlens.config.RESULTS_DB", database),
                patch(
                    "amlens.services.dashboard_service.load_dashboard_data", return_value=original
                ) as loader,
            ):
                app = AppTest.from_file(APP).run(timeout=30)
                state = app.session_state["amlens_observatory__state"]
                state["cursor"] = original.end
                state["statuses"] = {"0": {"status": "reviewed", "evidence_id": "first"}}
                app.run(timeout=30)
                self.assertEqual(
                    app.session_state["amlens_observatory__state"]["cursor"], original.end
                )
                loader.return_value = replacement
                app.run(timeout=30)
                self.assertEqual(list(app.exception), [])
                self.assertEqual(
                    app.session_state["amlens_observatory__state"]["cursor"], replacement.start - 1
                )
                self.assertEqual(app.session_state["amlens_observatory__state"]["statuses"], {})
                self.assertEqual(
                    app.session_state["amlens_observatory__dataset"], replacement.fingerprint
                )
                self.assertNotEqual(original.fingerprint, replacement.fingerprint)

    def test_missing_databases_show_preparation_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.sqlite"
            with (
                patch("amlens.config.OBSERVATION_DB", missing),
                patch("amlens.config.RESULTS_DB", missing),
            ):
                app = AppTest.from_file(APP).run(timeout=10)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.error), 1)
        self.assertIn("prepare_data.py", app.code[0].value)
        self.assertIn("detect_patterns.py", app.code[0].value)

    def test_loaded_dataset_renders_real_component_without_startup_exception(self):
        data = ReplayDataset(fixture_records())
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "present.sqlite"
            database.touch()
            with (
                patch("amlens.config.OBSERVATION_DB", database),
                patch("amlens.config.RESULTS_DB", database),
                patch("amlens.services.dashboard_service.load_dashboard_data", return_value=data),
            ):
                app = AppTest.from_file(APP).run(timeout=10)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        self.assertEqual(app.session_state["amlens_observatory__state"]["cursor"], data.start - 1)
        self.assertEqual(app.session_state["amlens_observatory__state"]["language"], "en")


if __name__ == "__main__":
    unittest.main()
