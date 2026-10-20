"""Read transaction data without evaluation labels."""

import sqlite3
from collections.abc import Iterable
from datetime import datetime


def _timestamp(value: str | datetime) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if isinstance(value, datetime) else value


def get_time_bounds(connection: sqlite3.Connection) -> tuple[str, str]:
    row = connection.execute("SELECT min(event_time), max(event_time) FROM transactions").fetchone()
    if row[0] is None:
        raise ValueError("Observation database contains no transactions")
    return row[0], row[1]


def count_transactions_before(connection: sqlite3.Connection, cutoff: str | datetime) -> int:
    return connection.execute(
        "SELECT count(*) FROM transactions WHERE event_time < ?", (_timestamp(cutoff),)
    ).fetchone()[0]


def get_transactions(
    connection: sqlite3.Connection,
    transaction_ids: Iterable[int],
    *,
    before: str | datetime | None = None,
) -> list[dict]:
    """Return each requested source row once. Sort by time, then source row order."""
    identifiers = sorted(set(transaction_ids))
    result = []
    # Keep the parameter count below the SQLite variable limit.
    for offset in range(0, len(identifiers), 800):
        chunk = identifiers[offset : offset + 800]
        placeholders = ",".join("?" for _ in chunk)
        sql = f"SELECT * FROM transactions WHERE transaction_id IN ({placeholders})"
        parameters = list(chunk)
        if before is not None:
            sql += " AND event_time < ?"
            parameters.append(_timestamp(before))
        result.extend(dict(row) for row in connection.execute(sql, parameters))
    return sorted(result, key=lambda row: (row["event_time"], row["transaction_id"]))


def get_account_transactions(
    connection: sqlite3.Connection,
    bank_id: str,
    account_number: str,
    *,
    before: str | datetime | None = None,
    limit: int = 200,
) -> list[dict]:
    if limit < 1:
        raise ValueError("limit must be positive")
    sql = """SELECT * FROM transactions
        WHERE ((sender_bank = ? AND sender_account = ?)
            OR (receiver_bank = ? AND receiver_account = ?))"""
    parameters = [str(int(bank_id)), account_number, str(int(bank_id)), account_number]
    if before is not None:
        sql += " AND event_time < ?"
        parameters.append(_timestamp(before))
    sql += " ORDER BY event_time DESC, transaction_id DESC LIMIT ?"
    parameters.append(limit)
    return [dict(row) for row in connection.execute(sql, parameters)]
