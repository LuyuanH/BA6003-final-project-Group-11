from pathlib import Path


# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Data folders. Assignment files are stored in the project folder.
RAW_DATA_DIR = PROJECT_ROOT
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
DB_DIR = PROJECT_ROOT / "data" / "db"
LOG_DIR = PROJECT_ROOT / "logs"

# Raw data files
TRANSACTIONS_PATH = RAW_DATA_DIR / "HI-Small_Trans.csv"
ACCOUNTS_PATH = RAW_DATA_DIR / "HI-Small_accounts.csv"

# Processed data file
ENTITY_DATA_PATH = (
    PROCESSED_DATA_DIR
    / "transactions_with_entities.parquet"
)
ENTITY_FEATURES_PATH = PROCESSED_DATA_DIR / "entity_features.parquet"
ALERTS_PATH = PROCESSED_DATA_DIR / "alerts.csv"
DATABASE_PATH = DB_DIR / "amlens.db"
PIPELINE_LOG_PATH = LOG_DIR / "pipeline.log"
# Preserve the original four-rule percentile; add cycle evidence separately.
ALERT_PERCENTILE = 0.975
MIN_CROSS_CURRENCY_TRANSACTIONS = 20
CYCLE_WINDOW_HOURS = 120
CYCLE_MIN_RATIO = 0.8
CYCLE_MAX_RATIO = 1.2
