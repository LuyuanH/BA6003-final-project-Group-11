"""Save detection batches and evidence versions. Keep each version unchanged."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

RESULT_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE batches (
    batch_id INTEGER PRIMARY KEY,
    cutoff TEXT NOT NULL UNIQUE,
    candidate_count INTEGER NOT NULL,
    seconds REAL NOT NULL,
    stats_json TEXT NOT NULL
);
CREATE TABLE evidence (
    case_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    family TEXT NOT NULL,
    group_id TEXT NOT NULL,
    first_trigger TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(rule_id, group_id, version)
);
CREATE TABLE evidence_transactions (
    case_id TEXT NOT NULL REFERENCES evidence(case_id),
    transaction_id INTEGER NOT NULL,
    PRIMARY KEY (case_id, transaction_id)
);
CREATE INDEX evidence_discovery ON evidence(first_trigger, rule_id, group_id, version);
CREATE INDEX evidence_structure ON evidence(rule_id, group_id, version);
CREATE INDEX evidence_transaction_id ON evidence_transactions(transaction_id);
"""


def create_results(path: Path) -> sqlite3.Connection:
    """Create a temporary result database. The caller publishes the database after completion."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(RESULT_SCHEMA)
    return connection


def set_metadata(connection: sqlite3.Connection, key: str, value: Any) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        (key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
    )


def save_batch(
    connection: sqlite3.Connection,
    cutoff: str,
    cases: list[dict[str, Any]],
    stats: dict[str, Any],
    seconds: float,
) -> int:
    """Save one cutoff and its new evidence versions in one transaction. Ignore a cutoff that already exists."""
    if connection.execute("SELECT 1 FROM batches WHERE cutoff=?", (cutoff,)).fetchone():
        return 0
    previous = connection.execute("SELECT MAX(cutoff) FROM batches").fetchone()[0]
    if previous and cutoff <= previous:
        raise ValueError("Detection cutoffs must increase monotonically.")
    added = 0
    with connection:
        # Evidence versions can share a discovery time.
        # Sort by end time, transaction count, and case ID to select a stable last version.
        for case in sorted(
            cases,
            key=lambda item: (
                item["rule_id"],
                item["evidence_group_id"],
                item["evidence_end"],
                len(item["transaction_ids"]),
                item["case_id"],
            ),
        ):
            if case["evidence_end"] >= cutoff:
                raise ValueError("Evidence includes data at or beyond its detection cutoff.")
            if connection.execute(
                "SELECT 1 FROM evidence WHERE case_id=?", (case["case_id"],)
            ).fetchone():
                continue
            group = case["evidence_group_id"]
            version = connection.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM evidence WHERE rule_id=? AND group_id=?",
                (case["rule_id"], group),
            ).fetchone()[0]
            payload = {**case, "first_trigger": cutoff, "evidence_version": version}
            connection.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    case["case_id"],
                    case["rule_id"],
                    case["family"],
                    group,
                    cutoff,
                    version,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )
            connection.executemany(
                "INSERT INTO evidence_transactions VALUES (?, ?)",
                [(case["case_id"], transaction_id) for transaction_id in case["transaction_ids"]],
            )
            added += 1
        connection.execute(
            "INSERT INTO batches(cutoff,candidate_count,seconds,stats_json) VALUES (?,?,?,?)",
            (cutoff, stats.get("candidate_count", 0), seconds, json.dumps(stats, sort_keys=True)),
        )
    return added


def detection_counts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Count all evidence versions. Do not limit counts to the current review queue."""
    rows = connection.execute("""
        SELECT e.family AS pattern,
               COUNT(DISTINCT t.transaction_id) AS transaction_count,
               COUNT(DISTINCT e.case_id) AS evidence_set_count,
               COUNT(DISTINCT e.rule_id || ':' || e.group_id) AS structure_count
        FROM evidence e JOIN evidence_transactions t USING(case_id)
        GROUP BY e.family ORDER BY e.family
    """).fetchall()
    counts = [dict(row) for row in rows]
    union = connection.execute("""
        SELECT 'UNION' AS pattern,
               COUNT(DISTINCT t.transaction_id) AS transaction_count,
               COUNT(DISTINCT e.case_id) AS evidence_set_count,
               COUNT(DISTINCT e.rule_id || ':' || e.group_id) AS structure_count
        FROM evidence e JOIN evidence_transactions t USING(case_id)
    """).fetchone()
    return [*counts, dict(union)]
