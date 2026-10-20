def validate_transactions(df):
    """
    Run basic validation checks on the processed transaction dataset.
    """

    required_columns = [
        "Timestamp",
        "From Bank",
        "From Account",
        "To Bank",
        "To Account",
        "Is Laundering",
        "From Entity ID",
        "From Entity Name",
        "To Entity ID",
        "To Entity Name",
    ]

    # Test 1: Dataset should not be empty
    assert len(df) > 0, "Validation failed: dataset is empty."

    # Test 2: Required columns should exist
    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    assert len(missing_columns) == 0, (
        f"Validation failed: missing columns {missing_columns}"
    )

    # Test 3: Calculate entity mapping coverage
    from_mapping_rate = (df["From Entity ID"] != "UNMAPPED").mean()
    to_mapping_rate = (df["To Entity ID"] != "UNMAPPED").mean()

    print("Validation results")
    print("------------------")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {df.shape[1]}")
    print(f"From Entity mapping rate: {from_mapping_rate:.2%}")
    print(f"To Entity mapping rate: {to_mapping_rate:.2%}")
    print(f"Positive transaction labels: {int(df['Is Laundering'].sum()):,}")
    print(f"Timestamp errors: {int(df['Timestamp'].isna().sum()):,}")
    print("Basic validation tests passed.")

    return {
        "from_mapping_rate": from_mapping_rate,
        "to_mapping_rate": to_mapping_rate,
    }
##We added validation checks after entity mapping to make sure the dataset is not empty, required fields are still present, and account-to-entity mapping coverage is reasonable.
# 我们检查三件事——数据有没有变空、关键字段有没有丢失、Entity mapping 的覆盖率是多少
