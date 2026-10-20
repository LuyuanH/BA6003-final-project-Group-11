"""Validate each file in a portable ZIP or extracted project directory."""

import argparse
import json
import zipfile
from pathlib import Path

from amlens.operations.bundle import verify_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report = verify_bundle(args.path.expanduser().resolve())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        report = {"passed": False, "failures": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
