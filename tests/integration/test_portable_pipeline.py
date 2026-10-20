"""Do import, detection, validation, and replay tests after project relocation. Use small CSV files."""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from amlens.db.replay_repository import read_replay_records
from amlens.ingestion.csv_reader import ACCOUNT_HEADER, TRANSACTION_HEADER
from amlens.presenters import minute_index
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import initial_state

SOURCE_ROOT = Path(__file__).resolve().parents[2]
QUERY_FUNCTIONS = {
    "find_fan_in_candidates",
    "find_fan_out_candidates",
    "find_cycle_candidates",
    "find_gather_scatter_candidates",
    "find_scatter_gather_candidates",
    "find_stack_candidates",
    "find_random_candidates",
}
# Record function calls through the unchanged command-line entry point.
# Use the actual detector and database functions.
PROFILE_RUNNER = """
import importlib
import json
import runpy
import sys
from pathlib import Path

script, trace_file = sys.argv[1:]
calls = set()
def record(frame, event, arg):
    if (event == 'call'
            and frame.f_globals.get('__name__') == 'amlens.db.pattern_queries'
            and frame.f_code.co_name.startswith('find_')):
        calls.add(frame.f_code.co_name)
sys.argv = [script]
sys.setprofile(record)
try:
    runpy.run_path(script, run_name='__main__')
finally:
    sys.setprofile(None)
    module = importlib.import_module('amlens.db.pattern_queries')
    Path(trace_file).write_text(json.dumps({
        'queries': sorted(calls), 'module_file': module.__file__,
    }), encoding='utf-8')
"""


class PortablePipelineTests(unittest.TestCase):
    def _run(self, command, *, environment, cwd, expected_exit=0):
        result = subprocess.run(
            [sys.executable, *command],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, expected_exit, result.stderr + result.stdout)
        return result

    def _write_csvs(self, raw_directory):
        raw_directory.mkdir(parents=True)
        rows = [
            [
                f"2022/09/01 {hour:02}:00",
                "001",
                "0001",
                "002",
                f"000{destination}",
                "100.00",
                "US Dollar",
                "100.00",
                "US Dollar",
                "ACH",
                str(destination % 2),
            ]
            for hour, destination in [(1, 2), (2, 3), (3, 4), (4, 5), (6, 6)]
        ]
        rows.extend(
            [
                [
                    "2022/09/01 10:00",
                    "001",
                    "0001",
                    "001",
                    "0001",
                    "100.00",
                    "US Dollar",
                    "100.00",
                    "US Dollar",
                    "ACH",
                    "0",
                ],
                [
                    "2022/09/01 13:00",
                    "003",
                    "0008",
                    "004",
                    "0009",
                    "9.25",
                    "Euro",
                    "9.25",
                    "Euro",
                    "Wire",
                    "0",
                ],
            ]
        )
        with (raw_directory / "HI-Small_Trans.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(TRANSACTION_HEADER)
            writer.writerows(rows)
        accounts = [
            ("001", "0001"),
            *[("002", f"000{i}") for i in range(2, 7)],
            ("003", "0008"),
            ("004", "0009"),
        ]
        with (raw_directory / "HI-Small_accounts.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(ACCOUNT_HEADER)
            writer.writerows(
                [
                    [f"银行 {bank}", bank, account, f"entity-{account}", f"账户 {account} α"]
                    for bank, account in accounts
                ]
            )
        # Use this file only for its hash. Do not include usable pattern labels.
        (raw_directory / "HI-Small_Patterns.txt").write_text(
            "Portable fixture — no annotation dependency.\n", encoding="utf-8"
        )

    def _semantic_result(self, records):
        return {
            "metadata": {
                key: records["metadata"][key]
                for key in ("status", "ruleset", "source_transactions", "observation_signature")
            },
            "batches": [
                {
                    "cutoff": row["cutoff"],
                    "candidate_count": row["candidate_count"],
                    "stats": json.loads(row["stats_json"]),
                }
                for row in records["batches"]
            ],
            "evidence": [
                {key: value for key, value in row.items() if key != "payload_json"}
                for row in records["evidence"]
            ],
            "timeline": records["timeline"],
            "transactions": records["transactions"],
            "accounts": records["accounts"],
        }

    def test_relocated_pipeline_is_causal_and_hash_seed_independent(self):
        with tempfile.TemporaryDirectory(prefix="amlens portable ") as directory:
            workspace = Path(directory)
            relocated = workspace / "移动 project"
            relocated.mkdir()
            shutil.copyfile(SOURCE_ROOT / "pyproject.toml", relocated / "pyproject.toml")
            shutil.copytree(
                SOURCE_ROOT / "src",
                relocated / "src",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
            )
            shutil.copytree(
                SOURCE_ROOT / "scripts",
                relocated / "scripts",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            shutil.copytree(SOURCE_ROOT / "tests" / "reference", relocated / "tests" / "reference")
            unrelated = workspace / "unrelated working directory"
            unrelated.mkdir()
            data_directory = workspace / "外部 data with spaces"
            self._write_csvs(data_directory / "raw")
            environment = {
                **os.environ,
                "AMLENS_DATA_DIR": str(data_directory),
                "PYTHONPATH": str(relocated / "src"),
                "PYTHONUTF8": "1",
                "PYTHONHASHSEED": "1",
            }
            self._run(
                [str(relocated / "scripts" / "prepare_data.py"), "--batch-size", "2"],
                environment=environment,
                cwd=unrelated,
            )
            observations = data_directory / "processed" / "amlens.sqlite"
            detections = data_directory / "processed" / "detection.sqlite"
            manifest = json.loads(
                observations.with_suffix(".manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual((manifest["transaction_count"], manifest["account_count"]), (7, 8))
            self.assertFalse((relocated / "data").exists())
            self.assertFalse((unrelated / "data").exists())

            runs = []
            for seed in ("1", "27"):
                trace = workspace / f"query-calls-{seed}.json"
                self._run(
                    [
                        "-c",
                        PROFILE_RUNNER,
                        str(relocated / "scripts" / "detect_patterns.py"),
                        str(trace),
                    ],
                    environment={**environment, "PYTHONHASHSEED": seed},
                    cwd=unrelated,
                )
                called = json.loads(trace.read_text(encoding="utf-8"))
                self.assertEqual(set(called["queries"]), QUERY_FUNCTIONS)
                self.assertTrue(Path(called["module_file"]).is_relative_to(relocated))
                records = read_replay_records(observations, detections)
                runs.append(self._semantic_result(records))
            self.assertEqual(runs[0], runs[1])
            self.assertEqual(records["metadata"]["status"], "complete")
            self.assertEqual(records["metadata"]["source_transactions"], 7)
            self.assertEqual(len(records["batches"]), 3)
            self.assertEqual(len(records["evidence"]), 2)
            transaction_times = {
                row["transaction_id"]: row["event_time"] for row in records["transactions"]
            }
            self.assertTrue(
                all(
                    transaction_times[identifier] < case["first_trigger"]
                    for case in records["evidence"]
                    for identifier in case["transaction_ids"]
                )
            )

            dataset = ReplayDataset(records)
            state = initial_state(dataset, 0)
            self.assertEqual(dashboard_snapshot(dataset, state)["queue"], [])
            state["cursor"] = minute_index("2022-09-01 06:00:00")
            first = dataset.visible(state)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].transactions, (1, 2, 3, 4))
            state["cursor"] = minute_index("2022-09-01 12:00:00")
            latest = dataset.visible(state)
            self.assertEqual(len(latest), 1)
            self.assertEqual(latest[0].group_id, first[0].group_id)
            self.assertEqual(latest[0].transactions, (1, 2, 3, 4, 5))
            state["cursor"] = dataset.end
            snapshot = dashboard_snapshot(dataset, state)
            self.assertEqual(
                (snapshot["processed"], snapshot["hold"], snapshot["pending"]), (7, 5, 1)
            )

            # This small dataset must fail the full reference comparison.
            # Select the database from the environment without a --database argument.
            result = self._run(
                [str(relocated / "scripts" / "verify_detection.py")],
                environment=environment,
                cwd=unrelated,
                expected_exit=1,
            )
            report = json.loads(result.stdout)
            self.assertTrue(report["checks"]["database_valid"])
            self.assertTrue(report["checks"]["complete"])
            self.assertFalse(report["checks"]["source_rows"])
            self.assertEqual(report["errors"], [])


if __name__ == "__main__":
    unittest.main()
