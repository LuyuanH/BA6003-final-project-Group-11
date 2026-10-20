"""Run the fixed ruleset on all batches in time order. Save the completed results."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from amlens.config import OBSERVATION_DB, RESULTS_DB
from amlens.db.connection import connect_observations
from amlens.db.detection_repository import (
    create_results,
    detection_counts,
    save_batch,
    set_metadata,
)


def checkpoints(first: datetime, last: datetime, step_hours: int = 6):
    """Generate cutoffs from midnight at the specified interval. Exclude transactions at the cutoff."""
    if step_hours <= 0:
        raise ValueError("Batch interval must be positive.")
    step = timedelta(hours=step_hours)
    cutoff = first.replace(hour=0, minute=0, second=0, microsecond=0) + step
    while cutoff <= last + step:
        yield cutoff
        cutoff += step


def source_signature(connection) -> str:
    """Use validated import metadata to link results to the source database."""
    rows = connection.execute("SELECT * FROM ingestion_metadata ORDER BY 1").fetchall()
    return hashlib.sha256(json.dumps([tuple(row) for row in rows]).encode()).hexdigest()


def run_detection(
    observation_path: Path = OBSERVATION_DB,
    results_path: Path = RESULTS_DB,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Recalculate results from observations. Do not read saved detections, labels, or pattern membership data."""
    from amlens.detection.engine import query
    from amlens.detection.rules import load_ruleset

    ruleset = load_ruleset()
    started = time.perf_counter()
    results_path = Path(results_path)
    if results_path.resolve() == Path(observation_path).resolve():
        raise ValueError("Detection output must differ from the observation database.")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".detection-", suffix=".sqlite", dir=results_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    observations = None
    output = None
    try:
        observations = connect_observations(observation_path)
        first, last, source_count = observations.execute(
            "SELECT MIN(event_time), MAX(event_time), COUNT(*) FROM transactions"
        ).fetchone()
        if not source_count:
            raise ValueError("The observations database contains no transactions.")
        output = create_results(temporary_path)
        set_metadata(output, "status", "running")
        set_metadata(output, "ruleset", ruleset)
        set_metadata(output, "observation_signature", source_signature(observations))
        set_metadata(output, "source_transactions", source_count)
        root = Path(__file__).resolve().parents[1]
        hashes = {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in (root / "detection", root / "db")
            for path in sorted(directory.rglob("*"))
            if path.suffix in (".py", ".sql", ".json")
        }
        set_metadata(output, "implementation_hashes", hashes)
        output.commit()
        cutoffs = list(
            checkpoints(
                datetime.fromisoformat(first),
                datetime.fromisoformat(last),
                ruleset["search_config"]["batch_hours"],
            )
        )
        for number, cutoff in enumerate(cutoffs, start=1):
            batch_start = time.perf_counter()
            cases, stats = query(cutoff, ruleset, con=observations)
            seconds = time.perf_counter() - batch_start
            added = save_batch(output, str(cutoff), cases, stats, seconds)
            if progress:
                progress(
                    {
                        "batch": number,
                        "total": len(cutoffs),
                        "cutoff": str(cutoff),
                        "new_evidence": added,
                        "seconds": round(seconds, 2),
                    }
                )
        summary = {
            "ruleset_version": ruleset["version"],
            "source_transactions": source_count,
            "batch_count": len(cutoffs),
            "first_cutoff": str(cutoffs[0]),
            "last_cutoff": str(cutoffs[-1]),
            "counts": detection_counts(output),
            "wall_seconds": round(time.perf_counter() - started, 2),
        }
        set_metadata(output, "summary", summary)
        set_metadata(output, "status", "complete")
        output.commit()
        output.close()
        output = None
        os.replace(temporary_path, results_path)
        results_path.with_suffix(".summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary
    finally:
        if observations is not None:
            observations.close()
        if output is not None:
            output.close()
        temporary_path.unlink(missing_ok=True)
