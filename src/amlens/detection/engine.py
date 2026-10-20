"""Generate candidate structures. Select candidates with SQLite queries and bound parameters."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from amlens.db.candidate_queries import window_edges
from amlens.db.pattern_queries import select_candidates
from amlens.detection.detectors.bipartite import detect_bipartite
from amlens.detection.detectors.cycle import detect_cycles
from amlens.detection.detectors.fan import detect_fans
from amlens.detection.detectors.gather_scatter import detect_gather_scatter
from amlens.detection.detectors.path import (
    bounded_graph,
    collect_two_hop_paths,
    detect_layered_paths,
)
from amlens.detection.detectors.scatter_gather import detect_scatter_gather
from amlens.detection.features import calculate_features
from amlens.detection.identity import case_hash, evidence_group_id
from amlens.detection.rules import load_ruleset


def generate(con: sqlite3.Connection, cutoff: datetime, config: dict) -> tuple[list[dict], dict]:
    """Return complete candidate structures without labels or pattern membership data."""
    cases = {}
    counts = defaultdict(int)
    for hours in config["windows_hours"]:
        edges = window_edges(con, cutoff, hours)
        counts["eligible_edge_window_records"] += len(edges)
        by_id = {e["transaction_id"]: e for e in edges}
        outgoing, incoming = defaultdict(list), defaultdict(list)
        roles = {}
        for edge in edges:
            outgoing[edge["src"]].append(edge)
            incoming[edge["dst"]].append(edge)
            roles[edge["src"]] = (
                edge["outgoing"],
                edge["incoming"],
                edge["outgoing_ach"],
                edge["incoming_ach"],
            )
            roles[edge["dst"]] = (
                edge["dst_outgoing"],
                edge["dst_incoming"],
                edge["dst_outgoing_ach"],
                edge["dst_incoming_ach"],
            )

        def emit(family: str, witness: list[dict], extra: dict | None = None) -> None:
            ids = tuple(sorted({e["transaction_id"] for e in witness}))
            key = (family, ids, hours)
            if len(ids) < 2 or key in cases:
                return
            evidence = [by_id[identifier] for identifier in ids]
            cases[key] = {
                "case_id": case_hash(family, ids),
                "family": family,
                "evidence_group_id": evidence_group_id(family, evidence),
                "transaction_ids": list(ids),
                "decision_time": cutoff.isoformat(sep=" "),
                "evidence_start": min(e["event_time"] for e in evidence).isoformat(sep=" "),
                "evidence_end": max(e["event_time"] for e in evidence).isoformat(sep=" "),
                "features": calculate_features(evidence, roles, hours, extra or {}),
            }

        detect_fans(incoming, outgoing, roles, config, emit)
        detect_gather_scatter(incoming, outgoing, roles, counts, emit)
        cap = config["max_graph_neighbors"]
        graph = bounded_graph(edges, incoming, outgoing, cap)
        counts["graph_edges_degree_excluded"] += len(edges) - len(graph)
        paths, graph_outgoing = collect_two_hop_paths(graph, config, counts)
        for pairs in paths.values():
            detect_scatter_gather(pairs, emit)
            detect_layered_paths(pairs, graph_outgoing, emit)
        detect_bipartite(incoming, outgoing, cap, counts, emit)
        detect_cycles(graph, config, counts, emit)
    return list(cases.values()), dict(counts)


def query(
    cutoff: datetime | str,
    ruleset: dict | None = None,
    observation_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> tuple[list[dict], dict]:
    """Run detection for one historical cutoff. The caller can reuse a read-only source connection."""
    from amlens.db.connection import connect_observations

    cutoff = datetime.fromisoformat(cutoff) if isinstance(cutoff, str) else cutoff
    ruleset = ruleset if ruleset is not None else load_ruleset()
    own_connection = con is None
    connection = (
        con
        if con is not None
        else (
            connect_observations(observation_path)
            if observation_path is not None
            else connect_observations()
        )
    )
    try:
        candidates, stats = generate(connection, cutoff, ruleset["search_config"])
        stats["candidate_count"] = len(candidates)
        return select_candidates(candidates, ruleset), stats
    finally:
        if own_connection:
            connection.close()
