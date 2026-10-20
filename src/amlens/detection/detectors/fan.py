"""Find complete fan-in and fan-out structures."""

from collections import defaultdict
from collections.abc import Callable


def detect_fans(incoming: dict, outgoing: dict, roles: dict, config: dict, emit: Callable) -> None:
    # Include all eligible incident edges for each currency group and a group with multiple currencies.
    # Use all payment methods for background fractions.
    for family, mapping, other in [("FAN-IN", incoming, "src"), ("FAN-OUT", outgoing, "dst")]:
        for hub, edges in mapping.items():
            if len({e[other] for e in edges}) < 3:
                continue
            groups = defaultdict(list)
            for e in edges:
                groups[e["paid_currency"]].append(e)
            groups["*"] = edges
            for group in groups.values():
                if (
                    3 <= len({e[other] for e in group}) <= config["max_graph_neighbors"]
                    and len(group) <= 64
                ):
                    r = roles[hub]
                    ach_fraction = r[3] / r[1] if family == "FAN-IN" else r[2] / r[0]
                    emit(family, group, {"hub_ach_fraction": ach_fraction})
