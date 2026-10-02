import pandas as pd


def build_entity_features(df):
    """
    Build entity-level AML features from transaction-level data.
    """

    # -----------------------------
    # 1. Sender-side aggregation
    # -----------------------------
    sent = (
        df.groupby(
            ["From Entity ID", "From Entity Name"],
            dropna=False
        )
        .agg(
            Sent_Transactions=("Timestamp", "count"),
            Sent_Laundering=("Is Laundering", "sum"),
            Unique_To_Entities=("To Entity ID", "nunique"),
            Unique_To_Banks=("To Bank", "nunique"),
            From_Account_Count=("From Account", "nunique"),
        )
        .reset_index()
        .rename(
            columns={
                "From Entity ID": "Entity_ID",
                "From Entity Name": "Entity_Name",
            }
        )
    )

    # -----------------------------
    # 2. Receiver-side aggregation
    # -----------------------------
    received = (
        df.groupby(
            ["To Entity ID", "To Entity Name"],
            dropna=False
        )
        .agg(
            Received_Transactions=("Timestamp", "count"),
            Received_Laundering=("Is Laundering", "sum"),
            Unique_From_Entities=("From Entity ID", "nunique"),
            Unique_From_Banks=("From Bank", "nunique"),
            To_Account_Count=("To Account", "nunique"),
        )
        .reset_index()
        .rename(
            columns={
                "To Entity ID": "Entity_ID",
                "To Entity Name": "Entity_Name",
            }
        )
    )

    # -----------------------------
    # 3. Combine sender + receiver
    # -----------------------------
    entity_features = sent.merge(
        received,
        on=["Entity_ID", "Entity_Name"],
        how="outer"
    )

    # Replace missing numeric values with 0
    numeric_columns = entity_features.select_dtypes(
        include="number"
    ).columns

    entity_features[numeric_columns] = (
        entity_features[numeric_columns].fillna(0)
    )

    # -----------------------------
    # 4. Create total indicators
    # -----------------------------
    entity_features["Total_Transactions"] = (
        entity_features["Sent_Transactions"]
        + entity_features["Received_Transactions"]
    )

    entity_features["Laundering_Transactions"] = (
        entity_features["Sent_Laundering"]
        + entity_features["Received_Laundering"]
    )

    entity_features["Total_Account_Count"] = (
        entity_features["From_Account_Count"]
        + entity_features["To_Account_Count"]
    )

    return entity_features