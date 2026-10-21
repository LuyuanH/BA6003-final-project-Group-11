"""Export and load complete replay records without the source databases."""

import gzip
import hashlib
import json
import os
import tempfile
import zlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from amlens.db.replay_repository import read_replay_records
from amlens.services.case_service import ReplayDataset

FORMAT_VERSION = 1
MAX_JSON_BYTES = 64 * 1024 * 1024


def _json_bytes(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _validate_records(records: dict) -> ReplayDataset:
    """Check references and time order before the dashboard can use the records."""
    if records["metadata"].get("status") != "complete":
        raise ValueError("Replay snapshot contains incomplete detection results.")
    timeline = records["timeline"]
    times = [datetime.fromisoformat(row[0]) for row in timeline]
    if not times or any(left >= right for left, right in zip(times, times[1:])):
        raise ValueError("Replay snapshot timeline is empty or out of order.")
    if any(type(row[1]) is not int or row[1] <= 0 for row in timeline):
        raise ValueError("Replay snapshot has invalid transaction counts.")
    if sum(row[1] for row in timeline) != records["metadata"]["source_transactions"]:
        raise ValueError("Replay snapshot transaction totals do not match.")
    cutoffs = [datetime.fromisoformat(row["cutoff"]) for row in records["batches"]]
    if not cutoffs or any(left >= right for left, right in zip(cutoffs, cutoffs[1:])):
        raise ValueError("Replay snapshot detection batches are empty or out of order.")
    transaction_ids = [row["transaction_id"] for row in records["transactions"]]
    if len(set(transaction_ids)) != len(transaction_ids):
        raise ValueError("Replay snapshot contains duplicate transactions.")
    evidence_ids = [row["case_id"] for row in records["evidence"]]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("Replay snapshot contains duplicate evidence versions.")
    for row in records["evidence"]:
        if not row["transaction_ids"] or not set(row["transaction_ids"]) <= set(transaction_ids):
            raise ValueError("Replay snapshot references missing transactions.")
        start, end, cutoff = (
            datetime.fromisoformat(row[key])
            for key in ("evidence_start", "evidence_end", "first_trigger")
        )
        if not start <= end < cutoff or cutoff > cutoffs[-1]:
            raise ValueError("Replay snapshot has invalid evidence time boundaries.")
    data = ReplayDataset(records)
    for case in data.evidence:
        # Validate account references and the exact values used by the UI and AI.
        data.detail(case, "pending")
    return data


def read_replay_snapshot(path: Path) -> ReplayDataset:
    """Read a versioned, checked snapshot. Never fall back to local databases."""
    try:
        with gzip.open(path, "rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("Replay snapshot exceeds the 64 MiB JSON limit.")
        envelope = json.loads(raw)
        if (
            type(envelope["format_version"]) is not int
            or envelope["format_version"] != FORMAT_VERSION
        ):
            raise ValueError("Unsupported replay snapshot format version.")
        records = envelope["records"]
        if hashlib.sha256(_json_bytes(records)).hexdigest() != envelope["sha256"]:
            raise ValueError("Replay snapshot checksum does not match.")
        accounts = records["accounts"]
        records["accounts"] = {(row["bank_id"], row["account_number"]): row for row in accounts}
        if len(records["accounts"]) != len(accounts):
            raise ValueError("Replay snapshot contains duplicate accounts.")
        return _validate_records(records)
    except (
        OSError,
        EOFError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
        zlib.error,
    ) as error:
        raise ValueError(
            "Cannot load the replay snapshot. Export it again with scripts/export_replay.py."
        ) from error


@lru_cache(maxsize=2)
def load_replay_snapshot(path: str, modified_ns: int, size: int) -> ReplayDataset:
    """Share immutable replay data. Reload after a snapshot file change."""
    return read_replay_snapshot(Path(path))


def export_replay_snapshot(observations: Path, detections: Path, output: Path) -> dict:
    """Validate both databases and atomically replace the deployment snapshot."""
    sources = (observations.resolve(), detections.resolve())
    output = output.resolve()
    if output in sources:
        raise ValueError("The snapshot destination must differ from the source databases.")

    def identities():
        return [
            (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            for s in (path.stat() for path in sources)
        ]

    before = identities()
    records = read_replay_records(*sources)
    data = _validate_records(records)
    if before != identities():
        raise ValueError("Source databases changed during export. Retry after detection stops.")
    records["accounts"] = [row for _, row in sorted(records["accounts"].items())]
    envelope = {
        "format_version": FORMAT_VERSION,
        "sha256": hashlib.sha256(_json_bytes(records)).hexdigest(),
        "records": records,
    }
    payload = _json_bytes(envelope)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("Replay snapshot exceeds the 64 MiB JSON limit.")
    compressed = gzip.compress(payload, mtime=0)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".replay-", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(compressed)
            stream.flush()
            os.fsync(stream.fileno())
        restored = read_replay_snapshot(temporary)
        if restored.fingerprint != data.fingerprint:
            raise ValueError("Replay identity changed during export.")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "snapshot": str(output),
        "format_version": FORMAT_VERSION,
        "compressed_bytes": len(compressed),
        "json_bytes": len(payload),
        "source_transactions": data.prefix[-1],
        "transactions": len(data.transactions),
        "accounts": len(data.accounts),
        "evidence_versions": len(data.evidence),
        "structure_groups": len({case.id for case in data.evidence}),
        "fingerprint": data.fingerprint,
    }
