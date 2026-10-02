from pathlib import Path


# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Data folders
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"

# Raw data files
TRANSACTIONS_PATH = RAW_DATA_DIR / "HI-Small_Trans.csv"
ACCOUNTS_PATH = RAW_DATA_DIR / "HI-Small_accounts.csv"

# Processed data file
ENTITY_DATA_PATH = (
    PROCESSED_DATA_DIR
    / "transactions_with_entities_temp.pkl"
)
