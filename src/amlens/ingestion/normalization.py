"""Convert source values to the database format. Keep account identities and original amount precision."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

SQLITE_MIN_INTEGER = -(2**63)
SQLITE_MAX_INTEGER = 2**63 - 1


def normalize_bank(value: str) -> str:
    return str(int(value))


def normalize_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("/", "-"))
    if parsed.tzinfo is not None:
        raise ValueError("Source timestamps must have no timezone")
    if parsed.second or parsed.microsecond:
        raise ValueError("Source timestamps must have minute precision")
    return parsed.isoformat(sep=" ", timespec="seconds")


def amount_to_cents(value: str) -> int:
    try:
        cents = Decimal(value) * 100
    except InvalidOperation as error:
        raise ValueError(f"Invalid monetary amount: {value!r}") from error
    if not cents.is_finite():
        raise ValueError(f"Amount must be finite: {value!r}")
    # Use DECIMAL(24,2) rounding for detection amounts.
    # Keep the original values separately because Bitcoin amounts can have six decimal places.
    result = int(cents.to_integral_value(rounding=ROUND_HALF_UP))
    if not SQLITE_MIN_INTEGER <= result <= SQLITE_MAX_INTEGER:
        raise ValueError(f"Monetary amount exceeds SQLite integer range: {value!r}")
    return result


def normalize_transaction(ordinal: int, row: list[str]) -> tuple:
    """Exclude the evaluation label from the observation database."""
    if not all(row[index] for index in (2, 4, 6, 8, 9)):
        raise ValueError("Account, currency, and payment format must not be empty")
    return (
        ordinal,
        normalize_timestamp(row[0]),
        normalize_bank(row[1]),
        row[2],
        normalize_bank(row[3]),
        row[4],
        amount_to_cents(row[5]),
        row[6],
        amount_to_cents(row[7]),
        row[8],
        row[9],
        row[5],
        row[7],
    )


def normalize_account(ordinal: int, row: list[str]) -> tuple:
    if not row[2]:
        raise ValueError("Account number must not be empty")
    return ordinal, normalize_bank(row[1]), row[2], row[3], row[4], row[0]
