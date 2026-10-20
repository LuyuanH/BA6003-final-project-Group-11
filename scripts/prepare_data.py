"""Import the two HI CSV files into SQLite."""

import argparse
import json
from pathlib import Path

from amlens.config import OBSERVATION_DB, RAW_DIR
from amlens.ingestion.import_service import prepare_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--database", type=Path, default=OBSERVATION_DB)
    parser.add_argument("--batch-size", type=int, default=25_000)
    arguments = parser.parse_args()
    manifest = prepare_data(
        arguments.raw_dir,
        arguments.database,
        batch_size=arguments.batch_size,
        progress=lambda message: print(message, flush=True),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
