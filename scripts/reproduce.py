"""Rebuild the historical demonstration. Validate every evidence set."""

import argparse
import json
import os
import shutil
import tempfile
from contextlib import closing
from pathlib import Path

from verify_detection import DEFAULT_REFERENCE, verify_results

from amlens.config import DATA_DIR
from amlens.db.connection import connect_observations
from amlens.db.replay_repository import read_replay_records
from amlens.ingestion.import_service import SOURCE_FILES, prepare_data, source_sha256
from amlens.operations.download import download_sources
from amlens.operations.environment import DATASET_MANIFEST, check_environment, check_sources
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.detection_service import run_detection
from amlens.services.replay_service import initial_state


def copy_sources(raw_dir: Path, target_dir: Path) -> None:
    """Copy source files. Keep the originals unchanged. Do not replace different target files."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_FILES:
        source, target = raw_dir / name, target_dir / name
        if source.resolve() == target.resolve():
            continue
        if target.exists():
            if source_sha256(source) == source_sha256(target):
                continue
            raise ValueError(f"Refusing to replace a different source file: {target}")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".copy-", dir=target_dir)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            if source_sha256(source) != source_sha256(temporary):
                raise ValueError(f"Source changed while copying: {source}")
            # Create the target only if it is still absent.
            # If the copy fails, remove only the file that this call created.
            with target.open("xb") as destination:
                try:
                    with temporary.open("rb") as source_stream:
                        shutil.copyfileobj(source_stream, destination, length=1024 * 1024)
                except BaseException:
                    destination.close()
                    target.unlink(missing_ok=True)
                    raise
        finally:
            temporary.unlink(missing_ok=True)


def validate_replay(observations: Path, detections: Path) -> dict:
    expected = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    with closing(connect_observations(observations)) as connection:
        manifest = json.loads(
            connection.execute(
                "SELECT value FROM ingestion_metadata WHERE key='manifest'"
            ).fetchone()[0]
        )
        source_matches = manifest.get("source_hashes") == {
            name: spec["sha256"] for name, spec in expected["files"].items()
        }
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    data = ReplayDataset(read_replay_records(observations, detections))
    state = initial_state(data, 0)
    state["cursor"] = data.end
    snapshot = dashboard_snapshot(data, state)
    result = {
        "processed": snapshot["processed"],
        "transactions": snapshot["hold"],
        "structures": len(snapshot["queue"]),
    }
    result["passed"] = (
        source_matches
        and integrity
        and result
        == {
            "processed": 5_078_345,
            "transactions": 330,
            "structures": 49,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--raw-dir", type=Path, help="Copy the three original HI files from this directory."
    )
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download missing inputs from the specified Kaggle version before the rebuild.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate existing results. Do not download files or rebuild databases.",
    )
    args = parser.parse_args()
    if args.download and args.verify_only:
        parser.error("--download cannot be combined with --verify-only (read-only validation).")
    data_dir = args.data_dir.expanduser().resolve()
    raw_dir = (args.raw_dir or data_dir / "raw").expanduser().resolve()
    if args.download:
        download_sources(raw_dir, progress=lambda message: print(message, flush=True))
    environment = check_environment(raw_dir, data_dir)
    print(json.dumps(environment, ensure_ascii=False, indent=2), flush=True)
    if not environment["passed"]:
        print(
            "Fix failed checks first; use uv sync --frozen and "
            "scripts/download_data.py to fetch the pinned HI files."
        )
        return 1
    observations = data_dir / "processed" / "amlens.sqlite"
    detections = data_dir / "processed" / "detection.sqlite"
    if not args.verify_only:
        copy_sources(raw_dir, data_dir / "raw")
        if not check_sources(data_dir / "raw")["passed"]:
            raise ValueError(
                "Copied source files differ from the frozen originals; rebuild stopped."
            )
        prepare_data(data_dir / "raw", observations, progress=lambda msg: print(msg, flush=True))
        run_detection(
            observations,
            detections,
            progress=lambda value: print(json.dumps(value), flush=True),
        )
    verification = verify_results(detections, args.reference)
    replay = validate_replay(observations, detections) if verification["passed"] else None
    report = {"verification": verification, "replay": replay}
    report["passed"] = verification["passed"] and bool(replay and replay["passed"])
    if report["passed"] and not args.verify_only:
        report["runtime"] = environment["runtime"]
        destination = data_dir / "processed" / "reproduction-report.json"
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Reproduction failed: {error}") from error
