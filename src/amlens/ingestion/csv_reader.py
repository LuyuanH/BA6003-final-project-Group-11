"""Read CSV columns by position. Keep the two Account columns separate."""

import csv
from collections.abc import Iterator
from pathlib import Path

TRANSACTION_HEADER = (
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
)
ACCOUNT_HEADER = ("Bank Name", "Bank ID", "Account Number", "Entity ID", "Entity Name")


def read_csv_batches(
    path: Path, expected_header: tuple[str, ...], batch_size: int = 25_000
) -> Iterator[list[tuple[int, list[str]]]]:
    """Yield batches within the size limit. Include the source row number and raw row. Start row numbers at one."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header != list(expected_header):
            raise ValueError(f"Unexpected CSV header in {path.name}: {header!r}")
        batch = []
        for ordinal, row in enumerate(reader, 1):
            if len(row) != len(expected_header):
                raise ValueError(
                    f"{path.name} data row {ordinal}: expected {len(expected_header)} columns"
                )
            batch.append((ordinal, row))
            if len(batch) == batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
