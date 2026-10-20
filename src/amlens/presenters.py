"""Convert application records to the data format that the dashboard uses."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

EPOCH = datetime(1970, 1, 1)  # The source does not specify a time zone.


def minute_index(value: str) -> int:
    return int((datetime.fromisoformat(value) - EPOCH).total_seconds() // 60)


def stamp(minute: float) -> str:
    return (EPOCH + timedelta(minutes=minute)).strftime("%Y/%m/%d %H:%M")


def account_key(bank: str | int, account: str) -> str:
    return f"{int(bank)}:{account}"


def transaction_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["transaction_id"],
        "time": minute_index(row["event_time"]),
        "timestamp": row["event_time"].replace("-", "/")[:16],
        "fromBank": row["sender_bank"],
        "from": row["sender_account"],
        "toBank": row["receiver_bank"],
        "to": row["receiver_account"],
        "paid": row.get("paid_raw") or format(Decimal(row["paid"]) / 100, ".2f"),
        "received": row.get("received_raw") or format(Decimal(row["received"]) / 100, ".2f"),
        "paymentCurrency": row["paid_currency"],
        "receivingCurrency": row["received_currency"],
        "format": row["payment_method"],
        # The CSV header is line 1. Add one to the transaction ID for the displayed CSV line.
        "lines": [row["transaction_id"] + 1],
    }


def account_record(row: dict[str, Any]) -> dict[str, str]:
    return {
        "key": account_key(row["bank_id"], row["account_number"]),
        "account": row["account_number"],
        "bankId": row["bank_id"],
        "bank": row["bank_name"],
        "entityId": row["entity_id"],
        "entity": row["entity_name"],
    }
