"""Validate the runtime environment and original HI file hashes. Keep the data unchanged."""

import argparse
import json
from pathlib import Path

from amlens.config import DATA_DIR
from amlens.operations.environment import check_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    raw_dir = args.raw_dir or data_dir / "raw"
    report = check_environment(raw_dir.expanduser().resolve(), data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
