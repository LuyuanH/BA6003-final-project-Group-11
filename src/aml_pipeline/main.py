"""Run the AMLens pipeline as a module or directly from VS Code."""

import logging
import sys
from pathlib import Path

# Direct file execution does not set a package context. Locate src relative
# to this file so the imports also work when launched from another folder.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "aml_pipeline"

from .build_entity_features import build_entity_features
from .config import LOG_DIR, PIPELINE_LOG_PATH
from .entity_mapping import map_entities
from .cycle_detection import detect_cycles
from .load_data import load_raw_data
from .risk_rules import build_alert_evidence, build_alerts
from .storage import save_pipeline_outputs
from .validation import validate_transactions


def run_pipeline() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(PIPELINE_LOG_PATH), logging.StreamHandler()],
    )
    log = logging.getLogger("amlens")
    try:
        log.info("Step 1/6: load source CSV files")
        transactions, accounts = load_raw_data()
        log.info("Loaded %s transactions and %s account records", f"{len(transactions):,}", f"{len(accounts):,}")

        log.info("Step 2/6: map bank accounts to entities")
        transactions = map_entities(transactions, accounts)

        log.info("Step 3/6: validate mapped transactions")
        validate_transactions(transactions)

        log.info("Step 4/6: build one-row-per-entity features")
        features = build_entity_features(transactions)

        log.info("Step 5/6: detect account cycles and apply six label-blind rules")
        paths, members, path_evidence = detect_cycles(transactions)
        log.info("Found %s closed paths", len(paths))
        alerts, thresholds = build_alerts(features, members)
        evidence = build_alert_evidence(transactions, alerts)
        log.info("Created %s alerts with %s evidence rows", f"{len(alerts):,}", f"{len(evidence):,}")

        log.info("Step 6/6: save dashboard outputs")
        save_pipeline_outputs(transactions, features, alerts, evidence, thresholds,
                              paths, members, path_evidence)
        log.info("Pipeline completed successfully")
    except Exception:
        log.exception("Pipeline failed")
        raise


if __name__ == "__main__":
    run_pipeline()
