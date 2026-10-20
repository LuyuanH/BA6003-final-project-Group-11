"""Do tests for evidence storage and time limits without the graph detector."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from amlens.db.detection_repository import create_results, detection_counts, save_batch
from amlens.services.detection_service import checkpoints


def evidence(identifier="case-a", ids=(1, 2), end="2022-09-01 03:00:00"):
    return {
        "case_id": identifier,
        "rule_id": "fan_in_v1",
        "family": "FAN-IN",
        "evidence_group_id": "group-a",
        "transaction_ids": list(ids),
        "evidence_start": "2022-09-01 01:00:00",
        "evidence_end": end,
        "features": {},
    }


class DetectionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.connection = create_results(Path(self.directory.name) / "results.sqlite")

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def test_updates_preserve_first_discovery_and_deduplicate_transactions(self):
        morning, noon = "2022-09-01 06:00:00", "2022-09-01 12:00:00"
        self.assertEqual(save_batch(self.connection, morning, [evidence()], {}, 1), 1)
        self.assertEqual(save_batch(self.connection, morning, [evidence()], {}, 1), 0)
        self.assertEqual(
            save_batch(self.connection, noon, [evidence(), evidence("case-b", (2, 3))], {}, 1), 1
        )
        rows = self.connection.execute(
            "SELECT first_trigger,version FROM evidence ORDER BY version"
        ).fetchall()
        self.assertEqual([tuple(row) for row in rows], [(morning, 1), (noon, 2)])
        union = detection_counts(self.connection)[-1]
        self.assertEqual(
            (union["transaction_count"], union["evidence_set_count"], union["structure_count"]),
            (3, 2, 1),
        )

    def test_future_evidence_rejects_entire_batch(self):
        cutoff = "2022-09-01 06:00:00"
        with self.assertRaises(ValueError):
            save_batch(self.connection, cutoff, [evidence(), evidence("case-b", end=cutoff)], {}, 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 0)

    def test_simultaneous_versions_prefer_latest_ending_complete_witness(self):
        save_batch(
            self.connection,
            "2022-09-01 06:00:00",
            [
                evidence("a", (1, 2, 3)),
                evidence("z", (1, 2)),
                evidence("b", (3, 4), end="2022-09-01 04:00:00"),
            ],
            {},
            1,
        )
        versions = self.connection.execute(
            "SELECT case_id FROM evidence ORDER BY version"
        ).fetchall()
        self.assertEqual([row[0] for row in versions], ["z", "a", "b"])

    def test_original_71_checkpoints_include_the_final_partial_day(self):
        points = list(checkpoints(datetime(2022, 9, 1), datetime(2022, 9, 18, 16, 18)))
        self.assertEqual(len(points), 71)
        self.assertEqual(points[-1], datetime(2022, 9, 18, 18))


if __name__ == "__main__":
    unittest.main()
