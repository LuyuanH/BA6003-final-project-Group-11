"""Build a complete, time-bounded case payload from trusted application records."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib.resources import files

from amlens.presenters import stamp
from amlens.services.case_service import EvidenceCase, ReplayDataset


@dataclass(frozen=True)
class Prompt:
    text: str
    version: str


def load_prompt(name: str = "prompt.txt") -> Prompt:
    text = files("amlens.analysis").joinpath(name).read_text(encoding="utf-8")
    return Prompt(text, "v1-" + hashlib.sha256(text.encode()).hexdigest()[:16])


def build_context(data: ReplayDataset, case: EvidenceCase) -> dict:
    detail = data.detail(case, "pending")
    detector = data.analysis_evidence[case.evidence_id]
    features = detector["features"]
    cutoff = datetime.fromisoformat(detector["decision_time"])
    hours = features.get("window_hours")
    start = cutoff - timedelta(hours=hours) if isinstance(hours, (int, float)) else None
    if cutoff > datetime.fromisoformat(stamp(case.discovered).replace("/", "-")):
        raise ValueError("Feature cutoff exceeds detection cutoff")
    context = {
        "case_id": f"C-{case.id + 1:04d}",
        "evidence_id": case.evidence_id,
        "evidence_version": case.version,
        "group_id": case.group_id,
        "detection_cutoff": stamp(case.discovered),
        "evidence_start": stamp(case.start),
        "evidence_end": stamp(case.end),
        "pattern": case.pattern,
        "rule_id": detector["rule_id"],
        "ruleset_version": detector["ruleset_version"],
        "rule_predicates": detector["predicates"],
        "features": features,
        "feature_cutoff": cutoff.isoformat(sep=" "),
        "feature_window_hours": hours,
        "feature_window_start": start.isoformat(sep=" ") if start else None,
        "accounts": detail["nodes"],
        "transactions": [
            {key: value for key, value in tx.items() if key not in ("time", "lines")}
            for tx in detail["transactions"]
        ],
        "payment_volume_by_currency": detail["amounts"],
        "limitations": [
            "Only this complete evidence version, not full account history.",
            "Business purpose, customer profile and beneficial ownership are unavailable.",
            "Missing account metadata may use account or bank IDs as placeholders.",
            "Historical detection rules have no established performance on unseen data.",
            "Source timestamps have no specified time zone; cutoff is exclusive.",
        ],
    }
    # Detach the worker's input from cached records and future UI activity.
    return json.loads(json.dumps(context, ensure_ascii=False, allow_nan=False))
