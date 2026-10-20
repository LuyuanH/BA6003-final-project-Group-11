"""Find cycles in time order. Apply search limits and remove directed dead ends."""

from collections import defaultdict, deque
from collections.abc import Callable


def detect_cycles(graph: list[dict], config: dict, counts: dict, emit: Callable) -> None:
    # Remove directed dead ends before the cycle search.
    gi, gout = defaultdict(set), defaultdict(set)
    for e in graph:
        gi[e["dst"]].add(e["src"])
        gout[e["src"]].add(e["dst"])
    active = set(gi) | set(gout)
    queue = deque(n for n in active if not gi[n] or not gout[n])
    while queue:
        n = queue.popleft()
        if n not in active:
            continue
        active.remove(n)
        for p in gi[n]:
            gout[p].discard(n)
            if not gout[p]:
                queue.append(p)
        for d in list(gout[n]):
            gi[d].discard(n)
            if not gi[d]:
                queue.append(d)
    cycle_edges = [e for e in graph if e["src"] in active and e["dst"] in active]
    co = defaultdict(list)
    for e in cycle_edges:
        co[e["src"]].append(e)
    expansions = 0
    for first in cycle_edges:
        stack = [(first["dst"], [first], {first["src"], first["dst"]})]
        while stack and expansions < config["max_cycle_expansions_per_window"]:
            node, path, visited = stack.pop()
            for nxt in co[node]:
                if nxt["event_time"] <= path[-1]["event_time"]:
                    continue
                expansions += 1
                if nxt["dst"] == first["src"]:
                    if len(path) >= 2:
                        emit("CYCLE", path + [nxt])
                elif nxt["dst"] not in visited and len(path) + 1 < config["max_cycle_hops"]:
                    stack.append((nxt["dst"], path + [nxt], visited | {nxt["dst"]}))
        if expansions >= config["max_cycle_expansions_per_window"]:
            counts["cycle_budget_exhausted_windows"] += 1
            break
    counts["cycle_expansions"] += expansions
