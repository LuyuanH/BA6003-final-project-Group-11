"""Control forward replay and evidence review within one browser session."""

import time
from typing import Any

from amlens.services.case_service import PATTERN_ORDER, ReplayDataset


def initial_state(data: ReplayDataset, now: float | None = None) -> dict[str, Any]:
    return {
        "start": data.start,
        "cursor": float(data.start - 1),
        "playing": False,
        "speed": 3600,
        "anchor": time.monotonic() if now is None else now,
        "selected": None,
        "view": "overview",
        "pattern": "",
        "language": "zh",
        "ui": {},
        "statuses": {},
        "revision": 0,
        "seen": [],
    }


def advance(state: dict[str, Any], data: ReplayDataset, now: float) -> None:
    if state["playing"]:
        state["cursor"] = min(
            data.end, state["cursor"] + max(0, now - state["anchor"]) * state["speed"] / 60
        )
        if state["cursor"] >= data.end:
            state["playing"] = False
    state["anchor"] = now


def apply_action(
    state: dict[str, Any], data: ReplayDataset, packet: Any, now: float | None = None
) -> None:
    """Validate dashboard events. Keep the replay clock active during navigation."""
    if not isinstance(packet, dict) or not isinstance(packet.get("id"), str):
        return
    if packet["id"] in state["seen"]:
        return
    state["seen"] = (state["seen"] + [packet["id"]])[-32:]
    now = time.monotonic() if now is None else now
    action, value = packet.get("action"), packet.get("value")
    if isinstance(packet.get("ui"), dict):
        state["ui"] = {
            key: packet["ui"][key]
            for key in ("caseId", "account", "tx", "tab", "search")
            if key in packet["ui"]
        }
    advance(state, data, now)
    if action == "play":
        state["playing"] = state["cursor"] < data.end
    elif action == "speed" and value in (900, 3600, 14400, 28800):
        state["speed"] = value
    elif action == "language" and value in ("zh", "en"):
        state["language"] = value
    elif action == "pattern" and value in ("", *PATTERN_ORDER):
        state["pattern"], state["selected"] = value, None
    elif action == "open" and isinstance(value, int) and not isinstance(value, bool):
        if any(case.id == value for case in data.visible(state)):
            state["selected"], state["view"] = value, "detail"
    elif action == "overview":
        state["view"] = "overview"
    elif action == "status" and value in ("pending", "investigating", "reviewed"):
        case = next((case for case in data.visible(state) if case.id == state["selected"]), None)
        # New evidence can arrive after a click and before the server receives the event.
        if case is not None and packet.get("evidenceId") == case.evidence_id:
            state["statuses"][str(case.id)] = {"status": value, "evidence_id": case.evidence_id}
    # Reject date, reset, next, and seek events from all callers.
    state["revision"] += 1
