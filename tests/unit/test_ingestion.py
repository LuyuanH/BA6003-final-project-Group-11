"""Make sure imports keep source identities and produce repeatable detection inputs."""

import csv
import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from amlens.db.account_repository import get_account
from amlens.db.connection import connect_observations
from amlens.db.transaction_repository import count_transactions_before, get_transactions
from amlens.ingestion.csv_reader import ACCOUNT_HEADER, TRANSACTION_HEADER
from amlens.ingestion.import_service import prepare_data
from amlens.ingestion.normalization import amount_to_cents


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "observations.sqlite"
        self.transaction = [
            "2022/09/01 00:20",
            "010",
            "000ABC",
            "002",
            "000XYZ",
            "0.29",
            "US Dollar",
            "1234.56",
            "Euro",
            "ACH",
            "1",
        ]
        self.write_transactions([self.transaction, self.transaction])
        self.write_csv(
            "HI-Small_accounts.csv",
            ACCOUNT_HEADER,
            [
                ["Bank Ten", "10", "000ABC", "E001", "Entity A"],
                ["Bank One", "1", "000UNUSED", "E002", "Entity B"],
            ],
        )

    def write_csv(self, name, header, rows):
        with (self.root / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    def write_transactions(self, rows):
        self.write_csv("HI-Small_Trans.csv", TRANSACTION_HEADER, rows)

    def test_import_preserves_identity_duplicates_precision_and_node_order(self):
        manifest = prepare_data(self.root, self.database, batch_size=1)
        self.assertEqual(manifest["transaction_count"], 2)
        self.assertEqual(manifest["account_count"], 2)
        with closing(connect_observations(self.database)) as connection:
            rows = get_transactions(connection, [2, 1, 2])
            self.assertEqual([row["transaction_id"] for row in rows], [1, 2])
            self.assertEqual(rows[0]["sender_account"], "000ABC")
            self.assertEqual(rows[0]["receiver_account"], "000XYZ")
            self.assertEqual(rows[0]["sender_bank"], "10")
            self.assertEqual(rows[0]["received"], 29)
            self.assertEqual(rows[0]["paid"], 123456)
            self.assertEqual(rows[0]["event_time"], "2022-09-01 00:20:00")
            self.assertEqual(
                [tuple(row) for row in connection.execute("SELECT * FROM nodes ORDER BY node_id")],
                [(1, "1", "000UNUSED"), (2, "10", "000ABC"), (3, "2", "000XYZ")],
            )
            edge = dict(connection.execute("SELECT * FROM edges LIMIT 1").fetchone())
            self.assertEqual((edge["src"], edge["dst"]), (2, 3))
            self.assertNotIn("label", rows[0])
            self.assertNotIn("label", edge)
            self.assertEqual(count_transactions_before(connection, "2022-09-01 00:20:00"), 0)
            self.assertEqual(count_transactions_before(connection, "2022-09-01 00:21:00"), 2)
            self.assertEqual(get_account(connection, "002", "000XYZ")["entity_name"], None)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM transactions")

    def test_repeat_replaces_instead_of_appending(self):
        prepare_data(self.root, self.database)
        manifest = prepare_data(self.root, self.database)
        self.assertEqual(manifest["transaction_count"], 2)
        with closing(connect_observations(self.database)) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM transactions").fetchone()[0], 2
            )

    def test_failed_import_preserves_existing_database(self):
        prepare_data(self.root, self.database)
        previous_hash = hashlib.sha256(self.database.read_bytes()).hexdigest()
        malformed = self.transaction.copy()
        malformed[5] = "not-an-amount"
        self.write_transactions([self.transaction, malformed])
        with self.assertRaisesRegex(ValueError, "data row 2"):
            prepare_data(self.root, self.database, batch_size=1)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), previous_hash)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_rejects_header_mismatch_and_invalid_amounts(self):
        self.write_csv("HI-Small_Trans.csv", ["wrong"], [["value"]])
        with self.assertRaisesRegex(ValueError, "Unexpected CSV header"):
            prepare_data(self.root, self.database)
        for invalid in ["NaN", "Infinity", "92233720368547758.08"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                amount_to_cents(invalid)
        self.assertEqual(amount_to_cents("92233720368547758.07"), 9223372036854775807)
        self.assertEqual(amount_to_cents("0.025852"), 3)
        self.assertEqual(amount_to_cents("-0.025"), -3)

    def test_preserves_original_high_precision_amounts(self):
        self.transaction[5] = "0.025852"
        self.transaction[6] = "Bitcoin"
        self.write_transactions([self.transaction])
        prepare_data(self.root, self.database)
        with closing(connect_observations(self.database)) as connection:
            transaction = get_transactions(connection, [1])[0]
            self.assertEqual(transaction["received"], 3)
            self.assertEqual(transaction["received_raw"], "0.025852")


if __name__ == "__main__":
    unittest.main()
