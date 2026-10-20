"""Do a startup test with the Streamlit entry point and component imports."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from amlens.services.case_service import ReplayDataset
from tests.unit.test_replay import fixture_records

APP = Path(__file__).resolve().parents[2] / "src/amlens/app.py"


class AppStartupTests(unittest.TestCase):
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
