"""Check snapshot integrity and preserve evidence and AI inputs through serialization."""

import gzip
import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from amlens.analysis.context import build_context
from amlens.analysis.overview import build_overview_context
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import initial_state
from amlens.services.snapshot_service import read_replay_snapshot
from tests.unit.test_replay import fixture_records


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "replay.json.gz"
        self.records = fixture_records()
        self.records["metadata"] = {"status": "complete", "source_transactions": 8}

    def write(self, records=None, version=1):
        records = deepcopy(self.records if records is None else records)
        records["accounts"] = list(records["accounts"].values())
        payload = json.dumps(
            records, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        envelope = {
            "format_version": version,
            "records": records,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        self.path.write_bytes(gzip.compress(json.dumps(envelope).encode()))

    def test_round_trip_preserves_all_versions_and_ai_inputs(self):
        original = ReplayDataset(self.records)
        self.write()
        restored = read_replay_snapshot(self.path)
        self.assertEqual(original.fingerprint, restored.fingerprint)
        for cursor in (
            original.start - 1,
            *(c.discovered for c in original.evidence),
            original.end,
        ):
            state = initial_state(original, 0)
            state["cursor"] = cursor
            self.assertEqual(
                dashboard_snapshot(original, state), dashboard_snapshot(restored, state)
            )
            self.assertEqual(
                build_overview_context(original, state), build_overview_context(restored, state)
            )
        for case in original.evidence:
            self.assertEqual(original.detail(case, "pending"), restored.detail(case, "pending"))
            self.assertEqual(build_context(original, case), build_context(restored, case))

    def test_corrupt_truncated_and_unsupported_snapshots_fail_closed(self):
        for payload in (b"not gzip", gzip.compress(b"not json"), gzip.compress(b"{}")[:-5]):
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, "Export it again"):
                    read_replay_snapshot(self.path)
        self.write(version=2)
        with self.assertRaises(ValueError) as error:
            read_replay_snapshot(self.path)
        self.assertIn("format version", str(error.exception.__cause__))

    def test_checksum_mismatch_is_rejected(self):
        self.write()
        envelope = json.loads(gzip.decompress(self.path.read_bytes()))
        envelope["records"]["timeline"][0][1] += 1
        self.path.write_bytes(gzip.compress(json.dumps(envelope).encode()))
        with self.assertRaises(ValueError) as error:
            read_replay_snapshot(self.path)
        self.assertIn("checksum", str(error.exception.__cause__))

    def test_missing_references_and_invalid_time_boundaries_are_rejected(self):
        changes = (
            lambda r: r["transactions"].pop(0),
            lambda r: r["accounts"].pop(("1", "1")),
            lambda r: r["evidence"][0].update(first_trigger="2022-09-01 02:00:00"),
            lambda r: r["timeline"].reverse(),
            lambda r: r["metadata"].update(source_transactions=99),
            lambda r: r["metadata"].update(status="running"),
        )
        for change in changes:
            with self.subTest(change=change):
                records = deepcopy(self.records)
                change(records)
                self.write(records)
                with self.assertRaises(ValueError):
                    read_replay_snapshot(self.path)


if __name__ == "__main__":
    unittest.main()
