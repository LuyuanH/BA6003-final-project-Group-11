"""Make sure replay validates the source records before it displays evidence."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from amlens.db.detection_repository import create_results, save_batch, set_metadata
from amlens.db.replay_repository import read_replay_records
from amlens.db.schema import create_observation_schema, finalize_observation_schema
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import initial_state


class ReplayRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.observations = Path(self.temp.name) / "observations.sqlite"
        self.detections = Path(self.temp.name) / "detections.sqlite"
        with closing(sqlite3.connect(self.observations)) as connection:
            create_observation_schema(connection)
            connection.execute("INSERT INTO ingestion_metadata VALUES ('source', 'test-fixture')")
            connection.executemany(
                "INSERT INTO accounts VALUES (?, '1', ?, ?, ?, 'Bank')",
                [(index, str(index), str(index), "Entity " + str(index)) for index in range(1, 4)],
            )
            connection.executemany(
                "INSERT INTO transactions VALUES (?, ?, '1', ?, '1', ?, 100, 'US Dollar', "
                "100, 'US Dollar', 'ACH', '1.00', '1.00')",
                [(1, "2022-09-01 01:00:00", "1", "2"), (2, "2022-09-01 02:00:00", "2", "3")],
            )
            finalize_observation_schema(connection)
            connection.commit()
            manifest = [
                tuple(row)
                for row in connection.execute("SELECT * FROM ingestion_metadata ORDER BY 1")
            ]
            signature = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
        with closing(create_results(self.detections)) as connection:
            set_metadata(connection, "status", "complete")
            set_metadata(connection, "observation_signature", signature)
            save_batch(
                connection,
                "2022-09-01 06:00:00",
                [
                    {
                        "case_id": "test",
                        "rule_id": "stack",
                        "family": "STACK",
                        "evidence_group_id": "group",
                        "evidence_start": "2022-09-01 01:00:00",
                        "evidence_end": "2022-09-01 02:00:00",
                        "transaction_ids": [1, 2],
                    }
                ],
                {},
                0.1,
            )

    def test_read_only_loading_preserves_sources_and_shapes(self):
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (self.observations, self.detections)
        }
        records = read_replay_records(self.observations, self.detections)
        data = ReplayDataset(records)
        state = initial_state(data, 0)
        self.assertEqual(dashboard_snapshot(data, state)["queue"], [])
        state["cursor"] = data.end
        snapshot = dashboard_snapshot(data, state)
        self.assertEqual((snapshot["processed"], snapshot["hold"], snapshot["pending"]), (2, 2, 1))
        self.assertEqual(snapshot["detail"]["pattern"], "STACK")
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_incomplete_detection_is_rejected(self):
        with closing(sqlite3.connect(self.detections)) as connection:
            set_metadata(connection, "status", "running")
            connection.commit()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            read_replay_records(self.observations, self.detections)

    def test_replaced_observations_require_redetection(self):
        with closing(sqlite3.connect(self.observations)) as connection:
            connection.execute("UPDATE ingestion_metadata SET value='replacement'")
            connection.commit()
        with self.assertRaisesRegex(ValueError, "different data version"):
            read_replay_records(self.observations, self.detections)


if __name__ == "__main__":
    unittest.main()
