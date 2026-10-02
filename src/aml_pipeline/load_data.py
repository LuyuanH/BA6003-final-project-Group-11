import pandas as pd

from .config import TRANSACTIONS_PATH, ACCOUNTS_PATH


def load_raw_data():
    """
    Load raw AML transaction and account datasets.
    """

    transactions = pd.read_csv(TRANSACTIONS_PATH)
    accounts = pd.read_csv(ACCOUNTS_PATH)

    print(f"Transactions loaded: {transactions.shape}")
    print(f"Accounts loaded: {accounts.shape}")

    return transactions, accounts


if __name__ == "__main__":
    load_raw_data()