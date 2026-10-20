"""Find gather-scatter structures at each local change from incoming to outgoing transactions."""

from collections.abc import Callable


def detect_gather_scatter(ins: dict, outs: dict, roles: dict, counts: dict, emit: Callable) -> None:
    # Use the local change from incoming to outgoing transactions as the phase boundary.
    for hub in ins.keys() & outs.keys():
        incoming, outgoing = ins[hub], outs[hub]
        if len(incoming) + len(outgoing) > 64:
            counts["gather_hubs_size_excluded"] += 1
            continue
        if len({e["src"] for e in incoming}) >= 2 and len({e["dst"] for e in outgoing}) >= 2:
            for split in sorted({e["event_time"] for e in outgoing}):
                left = [e for e in incoming if e["event_time"] < split]
                right = [e for e in outgoing if e["event_time"] >= split]
                if len({e["src"] for e in left}) >= 2 and len({e["dst"] for e in right}) >= 2:
                    emit(
                        "GATHER-SCATTER",
                        left + right,
                        {
                            "hub_ach_fraction": min(
                                roles[hub][2] / roles[hub][0], roles[hub][3] / roles[hub][1]
                            )
                        },
                    )
