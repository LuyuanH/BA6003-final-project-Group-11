"""Read one time window and prepare candidate records for SQL queries."""

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from importlib.resources import files

FEATURE_COLUMNS = (
    "edges",
    "nodes",
    "currencies",
    "span_hours",
    "window_hours",
    "max_in",
    "max_out",
    "intermediaries",
    "max_pair_repeats",
    "min_role_ach_fraction",
    "mean_role_ach_fraction",
    "max_background_incidence",
    "min_background_incidence",
    "internal_max_background",
    "currency_switches",
    "compatible_pairs",
    "chronological_pairs",
    "edge_node_ratio",
    "density",
    "hub_ach_fraction",
)


def read_sql(name: str) -> str:
    """Read a SQL resource from the package. Use only internal resource names."""
    return files("amlens.db").joinpath("sql", name).read_text(encoding="utf-8")


def window_edges(con: sqlite3.Connection, cutoff: datetime, hours: int) -> list[dict]:
    """Return ACH candidates with background counts from all payment methods and exact amount ratios."""
    cursor = con.execute(
        read_sql("window.sql"),
        {
            "window_start": (cutoff - timedelta(hours=hours)).isoformat(sep=" "),
            "cutoff": cutoff.isoformat(sep=" "),
        },
    )
    columns = [column[0] for column in cursor.description]
    edges = []
    for row in cursor:
        edge = dict(zip(columns, row))
        edge["event_time"] = datetime.fromisoformat(edge["event_time"])
        # SQLite stores amounts as integer hundredths of each currency unit.
        # The common scale does not change ratios. Decimal keeps the division precision.
        edge["paid"] = Decimal(edge["paid"])
        edge["received"] = Decimal(edge["received"])
        edges.append(edge)
    return edges


def stage_candidates(candidates: list[dict]) -> sqlite3.Connection:
    """Prepare candidates for one cutoff in memory. Use an ordinal to separate equal IDs from different windows."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        numeric_columns = ", ".join(f'"{name}" REAL' for name in FEATURE_COLUMNS)
        connection.execute(
            "CREATE TABLE candidate_features (candidate_ordinal INTEGER PRIMARY KEY, "
            "case_id TEXT NOT NULL, family TEXT NOT NULL, "
            f"decision_time TEXT NOT NULL, {numeric_columns})"
        )
        connection.execute(
            "CREATE TABLE candidate_members (candidate_ordinal INTEGER NOT NULL, "
            "transaction_id INTEGER NOT NULL, "
            "PRIMARY KEY(candidate_ordinal, transaction_id)) WITHOUT ROWID"
        )
        connection.execute(
            "CREATE TABLE selected_candidates (candidate_ordinal INTEGER NOT NULL, "
            "rule_id TEXT NOT NULL, PRIMARY KEY(candidate_ordinal, rule_id)) WITHOUT ROWID"
        )
        placeholders = ",".join("?" for _ in range(4 + len(FEATURE_COLUMNS)))
        connection.executemany(
            f"INSERT INTO candidate_features VALUES ({placeholders})",
            (
                (
                    ordinal,
                    case["case_id"],
                    case["family"],
                    case["decision_time"],
                    *(case["features"].get(name) for name in FEATURE_COLUMNS),
                )
                for ordinal, case in enumerate(candidates)
            ),
        )
        connection.executemany(
            "INSERT INTO candidate_members VALUES (?, ?)",
            (
                (ordinal, transaction_id)
                for ordinal, case in enumerate(candidates)
                for transaction_id in case["transaction_ids"]
            ),
        )
        connection.execute("CREATE INDEX candidate_family ON candidate_features(family)")
        return connection
    except BaseException:
        connection.close()
        raise
