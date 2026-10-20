"""Create stable identifiers for evidence sets and structure groups."""

import hashlib
import json


def case_hash(family: str, transaction_ids: list[int] | tuple[int, ...]) -> str:
    """Create an identifier from the pattern family and complete evidence set."""
    value = family + ":" + ",".join(map(str, sorted(transaction_ids)))
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def evidence_group_id(family: str, evidence: list[dict]) -> str:
    """Group evidence by common structure accounts. Allow transaction members to change between versions."""
    sources = {edge["src"] for edge in evidence}
    destinations = {edge["dst"] for edge in evidence}
    if family == "FAN-IN":
        anchors = sorted(destinations)
    elif family in {"FAN-OUT", "BIPARTITE"}:
        anchors = sorted(sources)
    elif family == "GATHER-SCATTER":
        anchors = sorted(sources & destinations)
    elif family == "SCATTER-GATHER":
        anchors = [sorted(sources - destinations), sorted(destinations - sources)]
    else:
        anchors = sorted(sources | destinations)
    return hashlib.sha256((family + json.dumps(anchors)).encode()).hexdigest()[:24]
