

import pandas as pd


def build_entity_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate activity, counterparties, currencies, and labels by entity."""
    df = df.copy()
    df["Is_Cross_Currency"] = (
        df["Payment Currency"] != df["Receiving Currency"]
    ).astype("int8")

    sent = df.groupby(["From Entity ID", "From Entity Name"], dropna=False).agg(
        Sent_Transactions=("Transaction_ID", "size"),
        Sent_Laundering=("Is Laundering", "sum"),
        Sent_Amount=("Amount Paid", "sum"),
        Outgoing_Counterparties=("To Entity ID", "nunique"),
        From_Account_Count=("From Account", "nunique"),
        Sent_Cross_Currency=("Is_Cross_Currency", "sum"),
    ).reset_index().rename(columns={
        "From Entity ID": "Entity_ID", "From Entity Name": "Entity_Name"
    })

    received = df.groupby(["To Entity ID", "To Entity Name"], dropna=False).agg(
        Received_Transactions=("Transaction_ID", "size"),
        Received_Laundering=("Is Laundering", "sum"),
        Received_Amount=("Amount Received", "sum"),
        Incoming_Counterparties=("From Entity ID", "nunique"),
        To_Account_Count=("To Account", "nunique"),
        Received_Cross_Currency=("Is_Cross_Currency", "sum"),
    ).reset_index().rename(columns={
        "To Entity ID": "Entity_ID", "To Entity Name": "Entity_Name"
    })

    features = sent.merge(received, on=["Entity_ID", "Entity_Name"], how="outer")
    numeric = features.select_dtypes(include="number").columns
    features[numeric] = features[numeric].fillna(0)
    count_columns = [c for c in numeric if c not in ("Sent_Amount", "Received_Amount")]
    features[count_columns] = features[count_columns].astype("int64")

    # The same transaction has two participants. For volume KPIs use sender-side
    # counts; Total_Transactions below is participant activity, not unique rows.
    features["Total_Transactions"] = (
        features["Sent_Transactions"] + features["Received_Transactions"]
    )
    features["Total_Amount"] = features["Sent_Amount"] + features["Received_Amount"]
    features["Known_Laundering_Entity"] = (
        features["Sent_Laundering"] + features["Received_Laundering"] > 0
    ).astype("int8")
    features["Cross_Currency_Transactions"] = (
        features["Sent_Cross_Currency"] + features["Received_Cross_Currency"]
    )
    features["Cross_Currency_Rate"] = (
        features["Cross_Currency_Transactions"]
        / features["Total_Transactions"].replace(0, 1)
    ).round(4)
    features["Entity_Type"] = (
        features["Entity_Name"].str.split(" #", n=1).str[0].fillna("Unknown")
    )
    return features.sort_values("Total_Transactions", ascending=False).reset_index(drop=True)
