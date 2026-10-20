"""Find bipartite candidates. The ruleset does not select these candidates."""

from collections import defaultdict
from collections.abc import Callable
from itertools import combinations


def detect_bipartite(ins: dict, outs: dict, cap: int, counts: dict, emit: Callable) -> None:
    # Find complete K2,k structures with separate source and destination layers.
    shared = defaultdict(set)
    for dst, incoming in ins.items():
        senders = sorted({e["src"] for e in incoming})
        if len(senders) > cap:
            counts["bipartite_destinations_degree_excluded"] += 1
            continue
        for s1, s2 in combinations(senders, 2):
            shared[s1, s2].add(dst)
    for (s1, s2), dests in shared.items():
        if 2 <= len(dests) <= cap and not ({s1, s2} & dests):
            witness = [e for s in (s1, s2) for e in outs[s] if e["dst"] in dests]
            if len(witness) <= 64:
                emit("BIPARTITE", witness)
