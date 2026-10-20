

import sqlite3

import pandas as pd

from .config import (
    ALERTS_PATH, DATABASE_PATH, ENTITY_FEATURES_PATH, LOG_DIR,
    PIPELINE_LOG_PATH, PROCESSED_DATA_DIR, ENTITY_DATA_PATH, DB_DIR,
)


def save_pipeline_outputs(
    transactions: pd.DataFrame,
    features: pd.DataFrame,
    alerts: pd.DataFrame,
    evidence: pd.DataFrame,
    thresholds: dict[str, float],
    paths: pd.DataFrame,
    members: pd.DataFrame,
    path_evidence: pd.DataFrame,
) -> None:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    transactions.to_parquet(ENTITY_DATA_PATH, index=False)
    features.to_parquet(ENTITY_FEATURES_PATH, index=False)
    alerts.to_csv(ALERTS_PATH, index=False)
    paths.to_parquet(PROCESSED_DATA_DIR / "cycle_paths.parquet", index=False)
    members.to_parquet(PROCESSED_DATA_DIR / "cycle_members.parquet", index=False)
    path_evidence.to_parquet(PROCESSED_DATA_DIR / "cycle_transactions.parquet", index=False)

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS review_status (
            Alert_ID TEXT PRIMARY KEY, Status TEXT NOT NULL DEFAULT 'Pending',
            Conclusion TEXT DEFAULT '', Note TEXT DEFAULT '', Updated_At TEXT DEFAULT ''
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS review_history (
            History_ID INTEGER PRIMARY KEY AUTOINCREMENT, Alert_ID TEXT NOT NULL,
            Status TEXT NOT NULL, Conclusion TEXT DEFAULT '', Note TEXT DEFAULT '',
            Changed_At TEXT NOT NULL
        )""")
        conn.execute("DROP TABLE IF EXISTS alerts")
        conn.execute("DROP TABLE IF EXISTS alert_evidence")
        alerts.to_sql("alerts", conn, if_exists="replace", index=False)
        if not evidence.empty:
            evidence.to_sql("alert_evidence", conn, if_exists="replace", index=False)
        else:
            pd.DataFrame(columns=["Alert_ID", "Transaction_ID"]).to_sql(
                "alert_evidence", conn, if_exists="replace", index=False
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_alert ON alert_evidence(Alert_ID)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_priority ON alerts(Priority)")
        paths.to_sql("cycle_paths", conn, if_exists="replace", index=False)
        members.to_sql("cycle_members", conn, if_exists="replace", index=False)
        path_evidence.to_sql("cycle_transactions", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cycle_member ON cycle_members(Entity_ID)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cycle_step ON cycle_transactions(Path_ID, Step)")
        conn.execute("""CREATE TABLE IF NOT EXISTS rule_thresholds (
            Rule_Name TEXT PRIMARY KEY, Threshold REAL NOT NULL
        )""")
        conn.execute("DELETE FROM rule_thresholds")
        conn.executemany(
            "INSERT INTO rule_thresholds(Rule_Name, Threshold) VALUES (?, ?)",
            [(str(k), float(v)) for k, v in thresholds.items()],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO review_status(Alert_ID) VALUES (?)",
            [(str(x),) for x in alerts["Alert_ID"]],
        )
        features.to_sql("entity_features", conn, if_exists="replace", index=False)
        conn.execute("DROP VIEW IF EXISTS entity_dashboard_cube")
        conn.execute("CREATE VIEW entity_dashboard_cube AS SELECT * FROM entity_features")
        daily = (
            transactions.assign(Date=transactions["Timestamp"].dt.date.astype(str))
            .groupby("Date", as_index=False)
            .agg(Transactions=("Transaction_ID", "size"),
                 Labelled_Transactions=("Is Laundering", "sum"))
        )
        daily.to_sql("daily_activity", conn, if_exists="replace", index=False)
