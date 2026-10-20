"""Calculate the transaction features that all structure detectors use."""

from collections import defaultdict


def calculate_features(es: list[dict], roles: dict, hours: int, extra: dict) -> dict:
    """Calculate features for one complete structure. Use background activity from all payment methods."""
    ins, outs = defaultdict(set), defaultdict(set)
    incidences = defaultdict(int)
    pair_counts = defaultdict(int)
    currencies = set()
    for e in es:
        ins[e["dst"]].add(e["src"])
        outs[e["src"]].add(e["dst"])
        incidences[e["src"]] += 1
        incidences[e["dst"]] += 1
        pair_counts[e["src"], e["dst"]] += 1
        currencies.add(e["paid_currency"])
    nodes = set(incidences)
    internal = set(ins) & set(outs)
    switches = 0
    comparisons = 0
    matching = 0
    for a in es:
        for b in es:
            if a["dst"] == b["src"] and a["event_time"] < b["event_time"]:
                comparisons += 1
                switches += a["received_currency"] != b["paid_currency"]
                matching += (
                    a["received_currency"] == b["paid_currency"]
                    and abs(float(b["paid"] / a["received"]) - 1) <= 0.2
                )
    case_role = []
    for n in nodes:
        r = roles[n]
        if outs[n]:
            case_role.append(r[2] / max(1, r[0]))
        if ins[n]:
            case_role.append(r[3] / max(1, r[1]))
    f = {
        "edges": len(es),
        "nodes": len(nodes),
        "currencies": len(currencies),
        "span_hours": (
            max(e["event_time"] for e in es) - min(e["event_time"] for e in es)
        ).total_seconds()
        / 3600,
        "window_hours": hours,
        "max_in": max(map(len, ins.values()), default=0),
        "max_out": max(map(len, outs.values()), default=0),
        "intermediaries": len(internal),
        "max_pair_repeats": max(pair_counts.values()),
        "min_role_ach_fraction": min(case_role),
        "mean_role_ach_fraction": sum(case_role) / len(case_role),
        "max_background_incidence": max(sum(roles[n][:2]) for n in nodes),
        "min_background_incidence": min(sum(roles[n][:2]) for n in nodes),
        "internal_max_background": max((sum(roles[n][:2]) for n in internal), default=0),
        "currency_switches": switches,
        "compatible_pairs": matching,
        "chronological_pairs": comparisons,
        "edge_node_ratio": len(es) / len(nodes),
        "density": len(pair_counts) / (len(nodes) * (len(nodes) - 1)),
    }
    f.update(extra)
    return f
