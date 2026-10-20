"""Create one portable ZIP with source code, original data, and validated results."""

import argparse
import json
from pathlib import Path

from reproduce import validate_replay
from verify_detection import verify_results

from amlens.config import DATA_DIR
from amlens.operations.bundle import (
    create_bundle,
    project_bundle_files,
    snapshot_bundle_files,
    verify_bundle,
)
from amlens.operations.environment import check_sources

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "dist" / "amlens-portable.zip"
    )
    parser.add_argument(
        "--without-results",
        action="store_true",
        help="Exclude result databases. Rebuild results after transfer.",
    )
    args = parser.parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    planned = project_bundle_files(PROJECT_ROOT, data_dir, include_results=not args.without_results)
    identities = snapshot_bundle_files(planned)
    if not check_sources(data_dir / "raw")["passed"]:
        raise ValueError("The three original HI files are missing or differ from the reference.")
    if not args.without_results:
        observations = data_dir / "processed" / "amlens.sqlite"
        detections = data_dir / "processed" / "detection.sqlite"
        if (
            not verify_results(detections)["passed"]
            or not validate_replay(observations, detections)["passed"]
        ):
            raise ValueError("Results failed validation. Run scripts/reproduce.py first.")
    output = args.output.expanduser().resolve()
    print("Packing source and data; this can take a minute.", flush=True)
    report = create_bundle(
        PROJECT_ROOT,
        data_dir,
        output,
        include_results=not args.without_results,
        expected_identities=identities,
    )
    report["verification"] = verify_bundle(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verification"]["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"Export failed: {error}") from error
