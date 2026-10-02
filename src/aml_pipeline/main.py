import logging

from .load_data import load_raw_data
from .entity_mapping import map_entities
from .validation import validate_transactions
from .build_entity_features import build_entity_features


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def run_pipeline():
    """
    Run the AML data processing pipeline.
    """

    # Step 1: Load raw data
    logger.info("Step 1: Loading raw data")

    transactions, accounts = load_raw_data()

    logger.info(
        f"Loaded {len(transactions):,} transactions "
        f"and {len(accounts):,} accounts"
    )

    # Step 2: Map accounts to entities
    logger.info("Step 2: Mapping accounts to entities")

    transactions_with_entities = map_entities(
        transactions,
        accounts
    )

    logger.info(
        f"Entity mapping completed: "
        f"{len(transactions_with_entities):,} transaction rows"
    )

    # Step 3: Validate processed transaction data
    logger.info("Step 3: Running validation checks")

    validation_results = validate_transactions(
        transactions_with_entities
    )

    logger.info(
        f"From Entity mapping rate: "
        f"{validation_results['from_mapping_rate']:.2%}"
    )

    logger.info(
        f"To Entity mapping rate: "
        f"{validation_results['to_mapping_rate']:.2%}"
    )

    # Step 4: Build entity-level features
    logger.info("Step 4: Building entity-level features")

    entity_features = build_entity_features(
        transactions_with_entities
    )

    logger.info(
        f"Entity feature table created: "
        f"{len(entity_features):,} entities"
    )

    logger.info("AML pipeline completed successfully")

    return transactions_with_entities, entity_features


if __name__ == "__main__":
    run_pipeline()