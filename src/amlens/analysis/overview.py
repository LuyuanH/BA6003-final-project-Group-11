"""Freeze aggregate dashboard data available at the current replay time."""

import hashlib
import json

from amlens.presenters import stamp
from amlens.services.dashboard_service import dashboard_snapshot


def build_overview_context(data, state, snapshot=None) -> dict:
    snapshot = snapshot if snapshot is not None else dashboard_snapshot(data, state)
    cursor = int(state["cursor"])
    visible = data.visible(state)
    detected = {tx for evidence in data.discovered_evidence(cursor) for tx in evidence.transactions}
    metrics = {
        "processed_transactions": snapshot["processed"],
        "held_transactions": snapshot["hold"],
        "detected_transactions": len(detected),
        "observed_cases": len(visible),
        "pending_cases": snapshot["pending"],
        "investigating_cases": snapshot["investigating"],
        "reviewed_cases": snapshot["reviewed"],
    }
    # Compare equal, fully observed six-hour intervals only after twelve hours of replay.
    if cursor - state["start"] + 1 >= 720:
        metrics["recent_6h_transactions"] = data.processed(cursor - 359, cursor)
        metrics["previous_6h_transactions"] = data.processed(cursor - 719, cursor - 360)
    for pattern in snapshot["patterns"]:
        prefix = pattern["id"].lower().replace("-", "_")
        metrics[prefix + ".active_cases"] = pattern["cases"]
        metrics[prefix + ".held_transactions"] = pattern["count"]
        metrics[prefix + ".detected_transactions"] = pattern["detectedCount"]
    context = {
        "as_of": snapshot["date"],
        "replay_start": stamp(state["start"]),
        "metrics": metrics,
        "patterns": snapshot["patterns"],
        "transaction_volume": [
            {"through": stamp(minute), "cumulative_transactions": count}
            for minute, count in snapshot["trend"]
        ],
        "cases": [
            {
                "id": case.id,
                "label": f"C-{case.id + 1:04d}",
                "pattern": case.pattern,
                "status": data.status(case, state),
                "evidence_version": case.version,
                "evidence_id": case.evidence_id,
                "discovered_at": stamp(case.discovered),
                "evidence_start": stamp(case.start),
                "evidence_end": stamp(case.end),
                "transaction_count": len(case.transactions),
            }
            for case in visible
        ],
        "limitations": [
            "Historical replay of fixed rules, not a live risk prediction or a fraud verdict.",
            "Processed volume covers all source transactions through the current replay time.",
            "Detected counts cover only evidence discovered by this time; detection is batched.",
            "Pattern transaction counts overlap and must not be added to obtain a total.",
            "Held counts include all discovered versions of unreviewed cases; case counts use "
            "only the latest complete version. Cases can share transactions.",
            "Reviewed is a workflow state, not proof that a case was legitimate or fraudulent.",
            "BIPARTITE is disabled: its zero count does not demonstrate absence of that pattern.",
            "The chart is a sampled cumulative count; use equal six-hour metrics for comparisons "
            "when present. Do not compare partial-day totals or infer long-term seasonality.",
            "Customer context, ground-truth labels and future evidence are not provided.",
        ],
    }
    return json.loads(json.dumps(context, ensure_ascii=False, allow_nan=False))


def overview_version(context: dict) -> str:
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[:20]
