"""Define observation tables. Store amounts as integer hundredths of each currency unit."""

import sqlite3

OBSERVATION_SCHEMA_VERSION = 1

RAW_SCHEMA = """
CREATE TABLE transactions (
    transaction_id INTEGER PRIMARY KEY,
    event_time TEXT NOT NULL,
    sender_bank TEXT NOT NULL,
    sender_account TEXT NOT NULL,
    receiver_bank TEXT NOT NULL,
    receiver_account TEXT NOT NULL,
    received INTEGER NOT NULL CHECK (typeof(received) = 'integer'),
    received_currency TEXT NOT NULL,
    paid INTEGER NOT NULL CHECK (typeof(paid) = 'integer'),
    paid_currency TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    received_raw TEXT NOT NULL,
    paid_raw TEXT NOT NULL
);
CREATE TABLE accounts (
    account_row_id INTEGER PRIMARY KEY,
    bank_id TEXT NOT NULL,
    account_number TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    bank_name TEXT NOT NULL
);
CREATE TABLE nodes (
    node_id INTEGER PRIMARY KEY,
    bank TEXT NOT NULL,
    account TEXT NOT NULL,
    UNIQUE (bank, account)
);
CREATE TABLE ingestion_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX transactions_event_time ON transactions (event_time, transaction_id);
CREATE INDEX transactions_sender ON transactions (sender_bank, sender_account, event_time);
CREATE INDEX transactions_receiver ON transactions (receiver_bank, receiver_account, event_time);
CREATE INDEX accounts_identity ON accounts (bank_id, account_number);
"""

EDGE_VIEW = """
CREATE VIEW edges AS
SELECT t.transaction_id, t.event_time, s.node_id AS src, d.node_id AS dst,
       t.received, t.received_currency, t.paid, t.paid_currency, t.payment_method
FROM transactions t
JOIN nodes s ON s.bank = t.sender_bank AND s.account = t.sender_account
JOIN nodes d ON d.bank = t.receiver_bank AND d.account = t.receiver_account;
"""


def create_observation_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(RAW_SCHEMA)
    connection.execute(f"PRAGMA user_version = {OBSERVATION_SCHEMA_VERSION}")


def finalize_observation_schema(connection: sqlite3.Connection) -> None:
    """Assign node identifiers in sorted order. Start the identifiers at one."""
    connection.executescript(INDEX_SCHEMA)
    connection.execute("""
        INSERT INTO nodes (node_id, bank, account)
        SELECT row_number() OVER (ORDER BY bank, account), bank, account
        FROM (
            SELECT sender_bank AS bank, sender_account AS account FROM transactions
            UNION SELECT receiver_bank, receiver_account FROM transactions
            UNION SELECT bank_id, account_number FROM accounts
        )
    """)
    connection.executescript(EDGE_VIEW)
    connection.execute("ANALYZE")
