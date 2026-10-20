"""Read account details. Include transaction accounts that the account CSV does not contain."""

import sqlite3
from collections.abc import Iterable

ACCOUNT_PROJECTION = """
    SELECT n.node_id, n.bank AS bank_id, n.account AS account_number,
           a.bank_name, a.entity_id, a.entity_name
    FROM nodes n
    LEFT JOIN accounts a ON a.account_row_id = (
        SELECT min(source.account_row_id) FROM accounts source
        WHERE source.bank_id = n.bank AND source.account_number = n.account
    )
"""


def get_accounts(connection: sqlite3.Connection, node_ids: Iterable[int]) -> list[dict]:
    identifiers = sorted(set(node_ids))
    result = []
    for offset in range(0, len(identifiers), 800):
        chunk = identifiers[offset : offset + 800]
        placeholders = ",".join("?" for _ in chunk)
        result.extend(
            dict(row)
            for row in connection.execute(
                ACCOUNT_PROJECTION + f" WHERE n.node_id IN ({placeholders})", chunk
            )
        )
    return sorted(result, key=lambda row: row["node_id"])


def get_account(connection: sqlite3.Connection, bank_id: str, account_number: str) -> dict | None:
    row = connection.execute(
        ACCOUNT_PROJECTION + " WHERE n.bank = ? AND n.account = ?",
        (str(int(bank_id)), account_number),
    ).fetchone()
    return dict(row) if row is not None else None
