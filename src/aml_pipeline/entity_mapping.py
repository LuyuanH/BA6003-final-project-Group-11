import pandas as pd


def map_entities(transactions, accounts):
    """
    Map sender and receiver bank accounts to Entity IDs and Entity Names.
    """

    # Work on a copy so the raw transaction dataframe is not modified
    transactions = transactions.copy()

    # Record row count before mapping
    rows_before_mapping = len(transactions)

    # Rename transaction account columns
    transactions = transactions.rename(
        columns={
            "Account": "From Account",
            "Account.1": "To Account"
        }
    )

    # Create sender lookup table
    from_lookup = accounts[
        ["Bank ID", "Account Number", "Entity ID", "Entity Name"]
    ].rename(
        columns={
            "Bank ID": "From Bank",
            "Account Number": "From Account",
            "Entity ID": "From Entity ID",
            "Entity Name": "From Entity Name"
        }
    )

    # Create receiver lookup table
    to_lookup = accounts[
        ["Bank ID", "Account Number", "Entity ID", "Entity Name"]
    ].rename(
        columns={
            "Bank ID": "To Bank",
            "Account Number": "To Account",
            "Entity ID": "To Entity ID",
            "Entity Name": "To Entity Name"
        }
    )

    # Map sender entities
    transactions = transactions.merge(
        from_lookup,
        on=["From Bank", "From Account"],
        how="left",
        validate="many_to_one"
    )

    # Map receiver entities
    transactions = transactions.merge(
        to_lookup,
        on=["To Bank", "To Account"],
        how="left",
        validate="many_to_one"
    )

    # Test: mapping should not change the number of transaction rows
    assert len(transactions) == rows_before_mapping, (
        "Validation failed: row count changed during entity mapping."
    )

    return transactions