"""Open database connections with the necessary read or write permissions."""

import sqlite3
from pathlib import Path

from amlens.config import OBSERVATION_DB


def connect_observations(path: Path | str = OBSERVATION_DB) -> sqlite3.Connection:
    """Open an existing observation database with read-only access. Do not create a missing database."""
    database = Path(path).resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Observation database not found: {database}")
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def connect_writable(path: Path | str) -> sqlite3.Connection:
    """Open a database with write access for imports or detection results."""
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection
