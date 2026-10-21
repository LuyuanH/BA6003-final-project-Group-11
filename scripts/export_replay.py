"""Export validated replay data for Streamlit Community Cloud."""

import argparse
import json
from pathlib import Path

from amlens.config import DATA_DIR
from amlens.services.snapshot_service import export_replay_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "deployment/replay.json.gz")
    args = parser.parse_args()
    processed = args.data_dir.expanduser().resolve() / "processed"
    report = export_replay_snapshot(
        processed / "amlens.sqlite", processed / "detection.sqlite", args.output.expanduser()
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"Replay export failed: {error}") from error
