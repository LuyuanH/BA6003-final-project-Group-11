"""Run detection offline. The web application reads only completed results."""

import argparse
import json
from pathlib import Path

from amlens.config import OBSERVATION_DB, RESULTS_DB
from amlens.services.detection_service import run_detection


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply seven fixed AML pattern rules in SQLite.")
    parser.add_argument("--database", type=Path, default=OBSERVATION_DB)
    parser.add_argument("--output", type=Path, default=RESULTS_DB)
    args = parser.parse_args()
    summary = run_detection(
        args.database,
        args.output,
        progress=lambda value: print(json.dumps(value), flush=True),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
