"""Import CSV files with source hashes and a limit on memory use. Replace the database after validation."""

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from amlens.config import OBSERVATION_DB, RAW_DIR
from amlens.db.connection import connect_writable
from amlens.db.schema import (
    OBSERVATION_SCHEMA_VERSION,
    create_observation_schema,
    finalize_observation_schema,
)
from amlens.ingestion.csv_reader import ACCOUNT_HEADER, TRANSACTION_HEADER, read_csv_batches
from amlens.ingestion.normalization import normalize_account, normalize_transaction

SOURCE_FILES = ("HI-Small_Trans.csv", "HI-Small_accounts.csv", "HI-Small_Patterns.txt")
TRANSACTION_INSERT = "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
ACCOUNT_INSERT = "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)"


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _import_rows(
    connection: sqlite3.Connection,
    path: Path,
    header: tuple[str, ...],
    normalize: Callable,
    insert: str,
    batch_size: int,
    progress: Callable[[str], None],
) -> int:
    count = 0
    for batch in read_csv_batches(path, header, batch_size):
        normalized = []
        for ordinal, row in batch:
            try:
                normalized.append(normalize(ordinal, row))
            except (ValueError, IndexError) as error:
                raise ValueError(f"{path.name} data row {ordinal}: {error}") from error
        connection.executemany(insert, normalized)
        connection.commit()
        count += len(normalized)
        if count % 500_000 < len(normalized):
            progress(f"{path.name}: {count:,} rows")
    return count


def prepare_data(
    raw_dir: Path | str = RAW_DIR,
    database_path: Path | str = OBSERVATION_DB,
    *,
    batch_size: int = 25_000,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Build and validate a temporary database. Replace the existing database in one operation."""
    started = time.perf_counter()
    raw_dir, database_path = Path(raw_dir), Path(database_path)
    progress = progress or (lambda message: None)
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    for name in SOURCE_FILES[:2]:
        if not (raw_dir / name).is_file():
            raise FileNotFoundError(raw_dir / name)
    source_hashes = {
        name: source_sha256(raw_dir / name) for name in SOURCE_FILES if (raw_dir / name).is_file()
    }
    source_stats = {name: (raw_dir / name).stat() for name in source_hashes}
    database_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.name}.", suffix=".tmp", dir=database_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    connection = None
    try:
        connection = connect_writable(temporary_path)
        # Use reduced durability only for this temporary database.
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = FILE")
        connection.execute("PRAGMA cache_size = -65536")
        create_observation_schema(connection)
        transaction_count = _import_rows(
            connection,
            raw_dir / SOURCE_FILES[0],
            TRANSACTION_HEADER,
            normalize_transaction,
            TRANSACTION_INSERT,
            batch_size,
            progress,
        )
        account_count = _import_rows(
            connection,
            raw_dir / SOURCE_FILES[1],
            ACCOUNT_HEADER,
            normalize_account,
            ACCOUNT_INSERT,
            batch_size,
            progress,
        )
        if not transaction_count or not account_count:
            raise ValueError("Transaction and account CSV files must contain data rows")
        progress("Building account mapping and indexes")
        finalize_observation_schema(connection)
        observed = connection.execute(
            "SELECT count(*) AS count, min(event_time) AS first_event, "
            "max(event_time) AS last_event FROM transactions"
        ).fetchone()
        if observed["count"] != transaction_count:
            raise ValueError("Transaction row count mismatch")
        if connection.execute("SELECT count(*) FROM accounts").fetchone()[0] != account_count:
            raise ValueError("Account row count mismatch")
        if connection.execute("SELECT count(*) FROM edges").fetchone()[0] != transaction_count:
            raise ValueError("Account mapping dropped or duplicated transaction rows")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity verification failed")
        for name, previous in source_stats.items():
            current = (raw_dir / name).stat()
            if (current.st_size, current.st_mtime_ns) != (previous.st_size, previous.st_mtime_ns):
                raise ValueError(f"Source changed during import: {name}")
        manifest = {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_hashes": source_hashes,
            "transaction_count": transaction_count,
            "account_count": account_count,
            "node_count": connection.execute("SELECT count(*) FROM nodes").fetchone()[0],
            "first_event": observed["first_event"],
            "last_event": observed["last_event"],
            "transaction_id": "Number CSV data rows from one. Keep duplicate rows as separate transactions.",
            "amount_unit": "Store integer hundredths of each currency unit. Use HALF_UP rounding to two decimal places.",
            "original_amounts": "Keep original CSV amounts as text in received_raw and paid_raw.",
            "timestamps": "Use source local timestamps without time zone conversion.",
            "labels": "Exclude evaluation labels from the observation database.",
            "seconds": round(time.perf_counter() - started, 3),
        }
        encoded_manifest = json.dumps(manifest, ensure_ascii=False, indent=2)
        connection.execute(
            "INSERT INTO ingestion_metadata (key, value) VALUES (?, ?)",
            ("manifest", encoded_manifest),
        )
        connection.commit()
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.close()
        connection = None
        with temporary_path.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary_path, database_path)
        manifest_path = database_path.with_suffix(".manifest.json")
        manifest_temp = manifest_path.with_suffix(".json.tmp")
        manifest_temp.write_text(encoded_manifest + "\n", encoding="utf-8")
        os.replace(manifest_temp, manifest_path)
        progress(f"Imported {transaction_count:,} transactions and {account_count:,} account rows")
        return manifest
    finally:
        if connection is not None:
            connection.close()
        temporary_path.unlink(missing_ok=True)
