"""Validate reference evidence. Detect damage to result databases and reference files."""

import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from amlens.db.detection_repository import create_results, save_batch, set_metadata
from amlens.detection.rules import load_ruleset

SOURCE_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = SOURCE_ROOT / "scripts" / "verify_detection.py"
SPEC = importlib.util.spec_from_file_location("verify_detection", SCRIPT)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class DetectionVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.baseline = Path(cls.workspace.name) / "baseline.sqlite"
        cls.reference_cases = json.loads(VERIFIER.DEFAULT_REFERENCE.read_text(encoding="utf-8"))
        # Use this fixture for verifier tests only.
        # Separate full-run tests cover graph detection.
        cases = []
        family_index = defaultdict(int)
        for case in cls.reference_cases:
            family = case["family"]
            group_count = 43 if family == "CYCLE" else 1
            group = family_index[family] % group_count
            family_index[family] += 1
            cases.append(
                {
                    **case,
                    "evidence_group_id": f"{family}-{group}",
                    "evidence_start": "2022-09-01 01:00:00",
                    "evidence_end": "2022-09-01 02:00:00",
                }
            )
        con = create_results(cls.baseline)
        try:
            for index in range(71):
                cutoff = str(datetime(2022, 9, 1, 6) + timedelta(hours=6 * index))
                save_batch(
                    con,
                    cutoff,
                    cases if index == 0 else [],
                    {"candidate_count": 3787421 if index == 0 else 0},
                    0.01,
                )
            for key, value in {
                "status": "complete",
                "ruleset": load_ruleset(),
                "source_transactions": 5078345,
                "summary": {"wall_seconds": 1.0},
            }.items():
                set_metadata(con, key, value)
            con.commit()
        finally:
            con.close()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "results.sqlite"
        shutil.copyfile(self.baseline, self.database)

    def tearDown(self):
        self.directory.cleanup()

    def test_complete_reference_result_passes_without_external_artifacts(self):
        report = VERIFIER.verify_results(self.database)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["missing_evidence"], 0)

    def test_missing_database_fails_without_creating_a_database(self):
        missing = Path(self.directory.name) / "missing.sqlite"
        report = VERIFIER.verify_results(missing)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["database_valid"])
        self.assertFalse(missing.exists())

    def test_invalid_sqlite_and_missing_tables_are_reported(self):
        for contents in [b"not a SQLite file", b""]:
            with self.subTest(contents=contents):
                self.database.write_bytes(contents)
                report = VERIFIER.verify_results(self.database)
                self.assertFalse(report["passed"])
                self.assertFalse(report["checks"]["database_valid"])
                self.assertTrue(report["errors"])

    def test_missing_or_corrupted_reference_fails(self):
        reference = Path(self.directory.name) / "reference.json"
        self.assertFalse(VERIFIER.verify_results(self.database, reference)["passed"])
        for contents in [
            "{",
            "{}",
            json.dumps(self.reference_cases[:-1]),
            json.dumps(self.reference_cases + [self.reference_cases[0]]),
        ]:
            with self.subTest(contents=contents[:20]):
                reference.write_text(contents, encoding="utf-8")
                report = VERIFIER.verify_results(self.database, reference)
                self.assertFalse(report["passed"])
                self.assertFalse(report["checks"]["reference_valid"])

    def test_reference_order_and_format_do_not_change_its_identity(self):
        reference = Path(self.directory.name) / "reformatted.json"
        reordered = [
            {**case, "transaction_ids": list(reversed(case["transaction_ids"]))}
            for case in reversed(self.reference_cases)
        ]
        reference.write_text(json.dumps(reordered, indent=1), encoding="utf-8")
        self.assertTrue(VERIFIER.verify_results(self.database, reference)["passed"])

    def test_missing_evidence_is_detected(self):
        identifier = self.reference_cases[0]["case_id"]
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute("DELETE FROM evidence_transactions WHERE case_id=?", (identifier,))
            con.execute("DELETE FROM evidence WHERE case_id=?", (identifier,))
        report = VERIFIER.verify_results(self.database)
        self.assertFalse(report["passed"])
        self.assertEqual(report["missing_evidence"], 1)

    def test_relational_member_corruption_cannot_hide_behind_valid_payloads(self):
        case = self.reference_cases[0]
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute(
                "DELETE FROM evidence_transactions WHERE case_id=? AND transaction_id=?",
                (case["case_id"], case["transaction_ids"][0]),
            )
        report = VERIFIER.verify_results(self.database)
        self.assertTrue(report["checks"]["evidence_members_equal"])
        self.assertFalse(report["checks"]["relational_evidence_equal"])
        self.assertFalse(report["passed"])

    def test_malformed_payload_is_reported(self):
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute(
                "UPDATE evidence SET payload_json='{}' WHERE case_id=?",
                (self.reference_cases[0]["case_id"],),
            )
        self.assertFalse(VERIFIER.verify_results(self.database)["checks"]["database_valid"])

    def test_changed_rule_or_batch_cannot_pass_by_matching_totals(self):
        rules = load_ruleset()
        rules["rules"][0]["predicates"][0]["value"] += 1
        with closing(sqlite3.connect(self.database)) as con, con:
            set_metadata(con, "ruleset", rules)
            con.execute("UPDATE batches SET cutoff='2022-09-01 06:01:00' WHERE batch_id=1")
        report = VERIFIER.verify_results(self.database)
        self.assertTrue(report["checks"]["counts_equal"])
        self.assertFalse(report["checks"]["ruleset_equal"])
        self.assertFalse(report["checks"]["71_batches"])
        self.assertFalse(report["passed"])

    def test_cli_default_reference_works_from_another_directory(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--database", str(self.database)],
            cwd=self.directory.name,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["passed"])

    def test_cli_missing_database_returns_failure_json(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--database", str(self.database.with_name("missing"))],
            cwd=self.directory.name,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertFalse(json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
