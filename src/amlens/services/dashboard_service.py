"""Convert saved detection evidence to dashboard data."""

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from amlens.db.replay_repository import read_replay_records
from amlens.presenters import account_key, stamp
from amlens.services.case_service import PATTERN_NAMES, PATTERN_ORDER, ReplayDataset


@lru_cache(maxsize=2)
def load_dashboard_data(
    observations: str, detections: str, observation_modified: int, detection_modified: int
) -> ReplayDataset:
    """Cache source records. Reload the records when database modification times change."""
    return ReplayDataset(read_replay_records(Path(observations), Path(detections)))


def dashboard_snapshot(data: ReplayDataset, state: dict[str, Any]) -> dict[str, Any]:
    visible = data.visible(state)
    statuses = {case.id: data.status(case, state) for case in visible}
    held = set()
    pattern_transactions = {pattern: set() for pattern in PATTERN_ORDER}
    historical_transactions = {pattern: set() for pattern in PATTERN_ORDER}
    # Count all discovered evidence. Keep one complete version for the case details.
    for evidence in data.discovered_evidence(state["cursor"]):
        historical_transactions[evidence.pattern].update(evidence.transactions)
        if statuses[evidence.id] != "reviewed":
            held.update(evidence.transactions)
            pattern_transactions[evidence.pattern].update(evidence.transactions)
    pattern_cases = Counter(case.pattern for case in visible if statuses[case.id] != "reviewed")
    queue = []
    for case in reversed(visible):
        if statuses[case.id] == "reviewed":
            continue
        detail = data.detail(case, statuses[case.id])
        degree = Counter(
            account_key(tx[bank], tx[account])
            for tx in detail["transactions"]
            for bank, account in (("fromBank", "from"), ("toBank", "to"))
        )
        lead = max(detail["nodes"], key=lambda node: degree[node["key"]])
        queue.append(
            {
                "id": case.id,
                "pattern": case.pattern,
                "end": stamp(case.discovered),
                "count": len(case.transactions),
                "accounts": len(detail["nodes"]),
                "lead": lead,
                "status": statuses[case.id],
                "version": case.version,
                "search": " ".join(
                    node["account"] + " " + node["entity"] for node in detail["nodes"]
                ),
            }
        )
    selected = next((case for case in visible if case.id == state["selected"]), None)
    if selected is None:
        candidates = [
            case for case in visible if not state["pattern"] or case.pattern == state["pattern"]
        ]
        selected = candidates[-1] if candidates else None
    if (
        selected
        and state["pattern"]
        and state["view"] == "overview"
        and selected.pattern != state["pattern"]
    ):
        selected = next(
            (case for case in reversed(visible) if case.pattern == state["pattern"]), None
        )
    detail = data.detail(selected, statuses[selected.id]) if selected else None
    if detail:
        review = state["statuses"].get(str(selected.id), {})
        detail["review"] = review if statuses[selected.id] == "reviewed" else None
    end = int(state["cursor"])
    points = [[state["start"], 0]]
    step = max(1, (end - state["start"]) // 70)
    for minute in range(state["start"], end + 1, step):
        points.append([minute, data.processed(state["start"], minute)])
    if end >= state["start"] and points[-1][0] != end:
        points.append([end, data.processed(state["start"], end)])
    return {
        "state": {
            key: value for key, value in state.items() if key not in ("anchor", "statuses", "seen")
        },
        "date": stamp(max(state["start"], state["cursor"])),
        "startDate": stamp(state["start"])[:10].replace("/", "-"),
        "rangeEnd": data.end,
        "rangeStart": data.start,
        "processed": data.processed(state["start"], state["cursor"]),
        "hold": len(held),
        "pending": sum(row["status"] == "pending" for row in queue),
        "investigating": sum(row["status"] == "investigating" for row in queue),
        "reviewed": sum(status == "reviewed" for status in statuses.values()),
        "patterns": [
            {
                "id": pattern,
                "name": PATTERN_NAMES[index],
                "count": len(pattern_transactions[pattern]),
                "cases": pattern_cases[pattern],
                "enabled": pattern != "BIPARTITE",
                "detectedCount": len(historical_transactions[pattern]),
            }
            for index, pattern in enumerate(PATTERN_ORDER)
        ],
        "queue": queue,
        "detail": detail,
        "trend": points,
        "dates": [stamp(data.start)[:10].replace("/", "-")],
        "sourceMode": "offline_detection_replay",
    }
