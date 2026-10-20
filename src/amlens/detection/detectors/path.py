"""Find paths in time order for layered structures and currency changes. Apply search limits."""

from collections import defaultdict
from collections.abc import Callable


def bounded_graph(edges: list[dict], incoming: dict, outgoing: dict, cap: int) -> list[dict]:
    """Remove branches that exceed the eligible neighbor limit."""
    neighbors = {
        node: len({e["src"] for e in incoming[node]} | {e["dst"] for e in outgoing[node]})
        for node in set(incoming) | set(outgoing)
    }
    return [e for e in edges if neighbors[e["src"]] <= cap and neighbors[e["dst"]] <= cap]


def collect_two_hop_paths(graph: list[dict], config: dict, counts: dict) -> tuple[dict, dict]:
    """Keep source order. Apply the fixed total limit on path expansions."""
    outgoing = defaultdict(list)
    for edge in graph:
        outgoing[edge["src"]].append(edge)
    paths = defaultdict(list)
    path_count = 0
    for first in graph:
        for second in outgoing[first["dst"]]:
            if first["event_time"] < second["event_time"] and first["src"] != second["dst"]:
                path_count += 1
                if path_count > config["max_path_expansions_per_window"]:
                    break
                paths[first["src"], second["dst"]].append((first, second))
        if path_count > config["max_path_expansions_per_window"]:
            counts["path_budget_exhausted_windows"] += 1
            break
    counts["two_hop_paths"] += min(path_count, config["max_path_expansions_per_window"])
    return paths, outgoing


def _compatible(first: dict, second: dict) -> bool:
    # A currency change does not establish equal value across currencies.
    return (
        first["received_currency"] != second["paid_currency"]
        or abs(float(second["paid"] / first["received"]) - 1) <= 0.2
    )


def detect_layered_paths(pairs: list[tuple[dict, dict]], outgoing: dict, emit: Callable) -> None:
    """Return complete paths with two, three, or four edges. Do not repeat nodes."""
    for first, second in pairs:
        if not _compatible(first, second):
            continue
        emit("STACK", [first, second])
        for third in outgoing[second["dst"]]:
            if (
                third["event_time"] > second["event_time"]
                and third["dst"] not in (first["src"], first["dst"])
                and _compatible(second, third)
            ):
                emit("STACK", [first, second, third])
                emit("RANDOM", [first, second, third])
                for fourth in outgoing[third["dst"]]:
                    if (
                        fourth["event_time"] > third["event_time"]
                        and fourth["dst"] not in (first["src"], first["dst"], second["dst"])
                        and _compatible(third, fourth)
                    ):
                        emit("STACK", [first, second, third, fourth])
                        emit("RANDOM", [first, second, third, fourth])
