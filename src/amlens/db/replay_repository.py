"""Read detection evidence and the full transaction timeline from SQLite."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def read_replay_records(observations: Path, detections: Path) -> dict[str, Any]:
    """Read detected transaction rows. Keep other transaction rows in SQLite."""
    with closing(_connect_readonly(detections)) as connection:
        metadata = {
            row["key"]: json.loads(row["value"])
            for row in connection.execute("SELECT key, value FROM metadata")
        }
        if metadata.get("status") != "complete":
            raise ValueError("Detection is incomplete. Run scripts/detect_patterns.py first.")
        batches = [dict(row) for row in connection.execute("SELECT * FROM batches ORDER BY cutoff")]
        evidence = [
            {**json.loads(row["payload_json"]), **dict(row)}
            for row in connection.execute(
                "SELECT * FROM evidence ORDER BY first_trigger, version, case_id"
            )
        ]
        ids = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT transaction_id FROM evidence_transactions ORDER BY transaction_id"
            )
        ]
    with closing(_connect_readonly(observations)) as connection:
        manifest = [
            tuple(row) for row in connection.execute("SELECT * FROM ingestion_metadata ORDER BY 1")
        ]
        signature = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
        if metadata.get("observation_signature") != signature:
            raise ValueError(
                "Detection results use a different data version. Rerun scripts/detect_patterns.py."
            )
        # Group rows by the indexed timestamp to keep one timeline entry per minute.
        timeline = [
            (row[0], row[1])
            for row in connection.execute(
                "SELECT event_time, COUNT(*) FROM transactions GROUP BY event_time ORDER BY event_time"
            )
        ]
        transactions = []
        accounts = {}
        for offset in range(0, len(ids), 500):
            chunk = ids[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            transactions.extend(
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM transactions WHERE transaction_id IN ({placeholders})", chunk
                )
            )
        keys = {
            (row[bank], row[account])
            for row in transactions
            for bank, account in (
                ("sender_bank", "sender_account"),
                ("receiver_bank", "receiver_account"),
            )
        }
        for bank, account in sorted(keys):
            row = connection.execute(
                "SELECT * FROM accounts WHERE bank_id = ? AND account_number = ?",
                (bank, account),
            ).fetchone()
            accounts[(bank, account)] = (
                dict(row)
                if row
                else {
                    "bank_id": bank,
                    "account_number": account,
                    "bank_name": bank,
                    "entity_id": "",
                    "entity_name": account,
                }
            )
    if len(transactions) != len(ids):
        raise ValueError(
            "Detection results reference transactions missing from the source database. "
            "Rerun offline detection."
        )
    return {
        "metadata": metadata,
        "batches": batches,
        "evidence": evidence,
        "timeline": timeline,
        "transactions": transactions,
        "accounts": accounts,
    }
