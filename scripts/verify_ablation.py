"""Check feature and rule ablations against prepared replay data without changing the databases."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from amlens.analysis.overview import build_overview_context
from amlens.config import OBSERVATION_DB, RESULTS_DB
from amlens.db.pattern_queries import select_candidates
from amlens.db.replay_repository import read_replay_records
from amlens.presenters import minute_index
from amlens.services.case_service import ReplayDataset
from amlens.services.replay_service import initial_state


def verify_ablations(observations: Path, detections: Path) -> dict:
    records = read_replay_records(observations, detections)
    data = ReplayDataset(records)
    state = initial_state(data, 0)
    without_features = deepcopy(data)
    for evidence in without_features.analysis_evidence.values():
        evidence["features"] = {}
        evidence["predicates"] = []
    cutoffs = [minute_index(batch["cutoff"]) for batch in records["batches"]]
    boundaries = sorted({data.end, *(time for cutoff in cutoffs for time in (cutoff - 1, cutoff))})
    checks = 0

    def require(condition, label):
        nonlocal checks
        if not condition:
            raise ValueError(f"Ablation failed: {label}")
        checks += 1

    timeline = [(minute_index(timestamp), count) for timestamp, count in records["timeline"]]
    for cursor in boundaries:
        state["cursor"] = cursor
        baseline = build_overview_context(data, state)
        prefix = deepcopy(records)
        prefix["evidence"] = [
            case for case in prefix["evidence"] if minute_index(case["first_trigger"]) <= cursor
        ]
        require(
            build_overview_context(ReplayDataset(prefix), state) == baseline,
            f"remove future evidence at {cursor}",
        )
        require(
            build_overview_context(without_features, state) == baseline,
            f"remove AI detector features at {cursor}",
        )
        filtered = {**state, "pattern": "CYCLE", "language": "zh", "ui": {"search": "no matches"}}
        require(
            build_overview_context(data, filtered) == baseline,
            f"change presentation filters at {cursor}",
        )
        require(
            baseline["metrics"]["processed_transactions"]
            == sum(count for minute, count in timeline if minute <= cursor),
            f"processed volume at {cursor}",
        )
        observed_ids = {tx for case in prefix["evidence"] for tx in case["transaction_ids"]}
        require(
            baseline["metrics"]["detected_transactions"] == len(observed_ids),
            f"unique detected transactions at {cursor}",
        )
        for metric, start, end in (
            ("recent_6h_transactions", cursor - 359, cursor),
            ("previous_6h_transactions", cursor - 719, cursor - 360),
        ):
            if metric in baseline["metrics"]:
                require(
                    baseline["metrics"][metric]
                    == sum(count for minute, count in timeline if start <= minute <= end),
                    f"{metric} at {cursor}",
                )

    # Reapply frozen rules to saved selected candidates. This isolates SQL selection;
    # synthetic detector-removal tests exercise candidate generation separately.
    candidates = [json.loads(case["payload_json"]) for case in records["evidence"]]
    ruleset = records["metadata"]["ruleset"]
    selected = select_candidates(candidates, ruleset)
    require(
        {(case["rule_id"], case["case_id"]) for case in selected}
        == {(case["rule_id"], case["case_id"]) for case in candidates},
        "all saved candidates still satisfy their frozen rules",
    )
    state["cursor"] = data.end
    full_overview = build_overview_context(data, state)
    variants = []
    for removed in ruleset["rules"]:
        family = removed["family"]
        ablated = select_candidates(
            candidates,
            {**ruleset, "rules": [rule for rule in ruleset["rules"] if rule != removed]},
        )
        require(
            ablated == [case for case in selected if case["rule_id"] != removed["rule_id"]],
            f"remove {family} rule without changing other selected evidence",
        )
        reduced = {
            **records,
            "evidence": [case for case in records["evidence"] if case["family"] != family],
        }
        overview = build_overview_context(ReplayDataset(reduced), state)
        for pattern in overview["patterns"]:
            if pattern["id"] != family:
                require(
                    pattern
                    == next(p for p in full_overview["patterns"] if p["id"] == pattern["id"]),
                    f"remove {family} without changing {pattern['id']} totals",
                )
        union = {tx for case in reduced["evidence"] for tx in case["transaction_ids"]}
        require(
            overview["metrics"]["detected_transactions"] == len(union), f"union without {family}"
        )
        require(overview["metrics"]["held_transactions"] == len(union), f"held without {family}")
        require(
            overview["metrics"]["processed_transactions"]
            == full_overview["metrics"]["processed_transactions"],
            f"source volume without {family}",
        )
        variants.append(
            {
                "removed_family": family,
                "remaining_evidence_sets": len(ablated),
                "remaining_detected_transactions": len(union),
                "passed": True,
            }
        )
    require(select_candidates(candidates, {**ruleset, "rules": []}) == [], "remove all rules")
    return {
        "passed": True,
        "scope": "Functional isolation on saved evidence; not an accuracy or model-quality evaluation.",
        "external_model_calls": 0,
        "dataset_fingerprint": data.fingerprint,
        "source_transactions": data.prefix[-1],
        "detection_batches": len(cutoffs),
        "evidence_sets": len(data.evidence),
        "replay_boundaries": len(boundaries),
        "checks_passed": checks,
        "boundary_variants": ["future evidence removed", "AI features removed", "filters changed"],
        "rule_variants": variants,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, default=OBSERVATION_DB)
    parser.add_argument("--detections", type=Path, default=RESULTS_DB)
    args = parser.parse_args()
    print(json.dumps(verify_ablations(args.observations, args.detections), indent=2))


if __name__ == "__main__":
    main()
