"""Account-level, time-ordered two- and three-edge closed paths.

Only transaction attributes enter detection. Currency/amount continuity is
checked at intermediary accounts, not inferred from labels or account balances.
"""

import numpy as np
import pandas as pd

from .config import CYCLE_WINDOW_HOURS, CYCLE_MIN_RATIO, CYCLE_MAX_RATIO


def find_flow_links(t: pd.DataFrame) -> pd.DataFrame:
    """Find all eligible incoming/outgoing pairs at the same bank/account."""
    incoming = t.rename(columns={
        "to_account": "account", "Amount Received": "amount",
        "Receiving Currency": "currency",
    })
    outgoing = t.rename(columns={
        "from_account": "account", "Amount Paid": "amount",
        "Payment Currency": "currency",
    })
    in_groups = incoming.groupby(["account", "currency"], sort=False).indices
    out_groups = outgoing.groupby(["account", "currency"], sort=False).indices
    ids = t.Transaction_ID.to_numpy()
    times = t.Timestamp.to_numpy().astype("datetime64[s]").astype("int64")
    received = incoming.amount.to_numpy()
    paid = outgoing.amount.to_numpy()
    pairs = []
    # Amount sorting avoids constructing a large unrestricted self-join.
    for key, out_positions in out_groups.items():
        in_positions = in_groups.get(key)
        if in_positions is None:
            continue
        order = in_positions[np.argsort(received[in_positions])]
        amounts = received[order]
        lower = np.searchsorted(amounts, paid[out_positions] / CYCLE_MAX_RATIO, side="left")
        upper = np.searchsorted(amounts, paid[out_positions] / CYCLE_MIN_RATIO, side="right")
        for position, lo, hi in zip(out_positions, lower, upper):
            possible = order[lo:hi]
            delay = times[position] - times[possible]
            possible = possible[(delay > 0) & (delay <= CYCLE_WINDOW_HOURS * 3600)]
            if len(possible):
                pairs.append(np.column_stack([
                    ids[possible], np.full(len(possible), ids[position]),
                ]))
    if not pairs:
        return pd.DataFrame(columns=["in_id", "out_id"], dtype="int64")
    return pd.DataFrame(np.concatenate(pairs), columns=["in_id", "out_id"])


def detect_cycles(transactions: pd.DataFrame):
    """Return path catalogue, participating entities, and ordered path evidence."""
    columns = [
        "Transaction_ID", "Timestamp", "From Bank", "From Account", "To Bank",
        "To Account", "From Entity ID", "To Entity ID", "Amount Paid",
        "Amount Received", "Payment Currency", "Receiving Currency",
    ]
    t = transactions[columns].copy()  # Explicitly excludes Is Laundering.
    t = t[
        t["From Entity ID"].ne(t["To Entity ID"])
        & t["From Entity ID"].ne("UNMAPPED") & t["To Entity ID"].ne("UNMAPPED")
        & t["Amount Paid"].gt(0) & t["Amount Received"].gt(0)
        & t.Timestamp.notna()
    ].copy()
    t["from_account"] = t["From Bank"].astype(str) + "|" + t["From Account"]
    t["to_account"] = t["To Bank"].astype(str) + "|" + t["To Account"]
    lookup = t.set_index("Transaction_ID")
    links = find_flow_links(t)
    two = links[
        links.in_id.map(lookup.from_account).eq(links.out_id.map(lookup.to_account))
    ]
    # Sharing the middle transaction guarantees account, currency and time
    # continuity across both intermediate accounts.
    three = links.merge(links, left_on="out_id", right_on="in_id", suffixes=("_1", "_2"))
    elapsed = (
        three.out_id_2.map(lookup.Timestamp) - three.in_id_1.map(lookup.Timestamp)
    ).dt.total_seconds() / 3600
    three = three[
        three.in_id_1.map(lookup.from_account).eq(three.out_id_2.map(lookup.to_account))
        & three.in_id_1.map(lookup["From Entity ID"]).ne(
            three.out_id_1.map(lookup["To Entity ID"]))
        & elapsed.le(CYCLE_WINDOW_HOURS)
    ]
    sequences = (
        [(int(a), int(b)) for a, b in two[["in_id", "out_id"]].itertuples(index=False, name=None)]
        + [(int(a), int(b), int(c)) for a, b, c in
           three[["in_id_1", "out_id_1", "out_id_2"]].itertuples(index=False, name=None)]
    )
    catalogue, participants, steps = [], [], []
    for sequence in sorted(set(sequences)):
        path_id = "C" + str(len(sequence)) + "-" + "-".join(map(str, sequence))
        path = lookup.loc[list(sequence)]
        rule = "ROUND_TRIP_2_EDGES" if len(sequence) == 2 else "CIRCULAR_3_EDGES"
        catalogue.append({
            "Path_ID": path_id, "Rule": rule, "Edge_Count": len(sequence),
            "Start_Time": path.Timestamp.iloc[0], "End_Time": path.Timestamp.iloc[-1],
            "Duration_Hours": (path.Timestamp.iloc[-1] - path.Timestamp.iloc[0]).total_seconds() / 3600,
            "Entity_Path": " → ".join(path["From Entity ID"].tolist() + [path["To Entity ID"].iloc[-1]]),
        })
        for entity in sorted(set(path["From Entity ID"]) | set(path["To Entity ID"])):
            participants.append({"Path_ID": path_id, "Entity_ID": entity, "Rule": rule})
        for step, transaction_id in enumerate(sequence, start=1):
            steps.append({"Path_ID": path_id, "Step": step, "Transaction_ID": transaction_id})
    paths = pd.DataFrame(catalogue, columns=[
        "Path_ID", "Rule", "Edge_Count", "Start_Time", "End_Time", "Duration_Hours", "Entity_Path",
    ])
    members = pd.DataFrame(participants, columns=["Path_ID", "Entity_ID", "Rule"])
    evidence = pd.DataFrame(steps, columns=["Path_ID", "Step", "Transaction_ID"])
    evidence = evidence.merge(transactions, on="Transaction_ID", how="left", validate="many_to_one")
    return paths, members, evidence
