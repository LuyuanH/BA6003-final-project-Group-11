

import pandas as pd

from .config import (
    ALERT_PERCENTILE,
    MIN_CROSS_CURRENCY_TRANSACTIONS,
)


def build_alerts(features: pd.DataFrame, cycle_members: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Keep four original triggers, add two cycle rules, assign review priority."""
    df = features[features["Entity_ID"] != "UNMAPPED"].copy()
    metrics = {"activity": "Sent_Transactions", "fan_out": "Outgoing_Counterparties",
               "fan_in": "Incoming_Counterparties"}
    thresholds = {name: float(df[column].quantile(ALERT_PERCENTILE))
                  for name, column in metrics.items()}
    two = set(cycle_members.loc[cycle_members.Rule.eq("ROUND_TRIP_2_EDGES"), "Entity_ID"])
    three = set(cycle_members.loc[cycle_members.Rule.eq("CIRCULAR_3_EDGES"), "Entity_ID"])
    conditions = {
        "HIGH_ACTIVITY": df.Sent_Transactions > thresholds["activity"],
        "FAN_OUT": df.Outgoing_Counterparties > thresholds["fan_out"],
        "FAN_IN": df.Incoming_Counterparties > thresholds["fan_in"],
        "CROSS_CURRENCY": (df.Sent_Cross_Currency >= MIN_CROSS_CURRENCY_TRANSACTIONS)
            & (df.Sent_Cross_Currency / df.Sent_Transactions.clip(lower=1) >= .5),
        "ROUND_TRIP_2_EDGES": df.Entity_ID.isin(two),
        "CIRCULAR_3_EDGES": df.Entity_ID.isin(three),
    }
    scale = conditions["HIGH_ACTIVITY"] | conditions["FAN_OUT"] | conditions["FAN_IN"]
    original = scale | conditions["CROSS_CURRENCY"]
    # Ordinal review policy. No additive risk score or probability is produced.
    df["Priority"] = "Low"
    df["Priority_Reason"] = "One original signal family: scale/breadth or currency."
    both = scale & conditions["CROSS_CURRENCY"]
    df.loc[both, ["Priority", "Priority_Reason"]] = ["Medium", "Both scale/breadth and currency signals."]
    df.loc[conditions["ROUND_TRIP_2_EDGES"], ["Priority", "Priority_Reason"]] = ["Medium", "Two-edge return path."]
    df.loc[conditions["ROUND_TRIP_2_EDGES"] & original, ["Priority", "Priority_Reason"]] = ["High", "Two-edge return path plus an original rule."]
    df.loc[conditions["CIRCULAR_3_EDGES"], ["Priority", "Priority_Reason"]] = ["High", "Three-edge closed path: direct High review priority."]
    reasons = pd.Series("", index=df.index, dtype="string")
    df["Rule_Count"] = 0
    for rule, condition in conditions.items():
        df["rule_" + rule] = condition
        df["Rule_Count"] += condition.astype(int)
        reasons += condition.map({True: rule + ", ", False: ""})
    df["Triggered_Rules"] = reasons.str.rstrip(", ")
    df["Alert_ID"] = "AL-" + df.Entity_ID.astype(str)
    columns = ["Alert_ID", "Entity_ID", "Entity_Name", "Entity_Type", "Priority",
               "Priority_Reason", "Rule_Count", "Triggered_Rules", "Sent_Transactions",
               "Outgoing_Counterparties", "Incoming_Counterparties", "Sent_Cross_Currency",
               "Known_Laundering_Entity"] + ["rule_" + r for r in conditions]
    alerts = df.loc[df.Rule_Count.gt(0), columns].copy()
    alerts["_order"] = alerts.Priority.map({"High": 0, "Medium": 1, "Low": 2})
    alerts = alerts.sort_values(["_order", "Entity_ID"]).drop(columns="_order").reset_index(drop=True)
    thresholds.update({"cross_currency_min_count": float(MIN_CROSS_CURRENCY_TRANSACTIONS),
                       "cross_currency_min_share": .5, "percentile": ALERT_PERCENTILE,
                       "cycle_window_hours": 120., "cycle_min_amount_ratio": .8,
                       "cycle_max_amount_ratio": 1.2})
    return alerts, thresholds


def build_alert_evidence(
    transactions: pd.DataFrame, alerts: pd.DataFrame, rows_per_alert: int = 10
) -> pd.DataFrame:
    """Keep the ten most recent linked transactions for each generated alert."""
    if alerts.empty:
        return pd.DataFrame()
    alert_entities = set(alerts["Entity_ID"])
    subset = transactions[
        transactions["From Entity ID"].isin(alert_entities)
        | transactions["To Entity ID"].isin(alert_entities)
    ].copy()
    sender = alerts[["Alert_ID", "Entity_ID"]].rename(
        columns={"Entity_ID": "From Entity ID"}
    )
    receiver = alerts[["Alert_ID", "Entity_ID"]].rename(
        columns={"Entity_ID": "To Entity ID"}
    )
    evidence = pd.concat([
        subset.merge(sender, on="From Entity ID", how="inner"),
        subset.merge(receiver, on="To Entity ID", how="inner"),
    ], ignore_index=True)
    keep = [
        "Alert_ID", "Transaction_ID", "Timestamp", "From Bank", "From Account",
        "To Bank", "To Account", "Amount Paid", "Payment Currency",
        "Amount Received", "Receiving Currency", "Payment Format", "Is Laundering",
        "From Entity ID", "From Entity Name", "To Entity ID", "To Entity Name",
    ]
    evidence = evidence.sort_values("Timestamp", ascending=False)
    evidence = evidence.groupby("Alert_ID", sort=False).head(rows_per_alert)
    return evidence[keep].reset_index(drop=True)
