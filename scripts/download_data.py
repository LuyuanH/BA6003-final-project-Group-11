"""Download the three specified Kaggle HI-Small files. Validate their contents."""

import argparse
import json
from pathlib import Path

from amlens.config import RAW_DIR
from amlens.operations.download import download_sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    report = download_sources(args.raw_dir, progress=lambda message: print(message, flush=True))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Download failed: {error}") from None
