"""Validate the Python environment and source files before data processing."""

import json
import platform
import shutil
import sqlite3
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from amlens.ingestion.import_service import source_sha256

DATASET_MANIFEST = Path(__file__).with_name("reference_dataset.json")


def check_sources(raw_dir: Path, manifest_path: Path = DATASET_MANIFEST) -> dict:
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {}
    for name, specification in expected["files"].items():
        path = raw_dir / name
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        digest = source_sha256(path) if exists and size == specification["bytes"] else None
        files[name] = {
            "exists": exists,
            "bytes": size,
            "sha256": digest,
            "matches": digest == specification["sha256"],
        }
    return {"passed": all(file["matches"] for file in files.values()), "files": files}


def check_environment(raw_dir: Path, data_dir: Path) -> dict:
    try:
        streamlit_version = version("streamlit")
    except PackageNotFoundError:
        streamlit_version = None
    sources = check_sources(raw_dir)
    existing_parent = data_dir.resolve()
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    free_bytes = shutil.disk_usage(existing_parent).free
    checks = {
        "python_3_13": sys.version_info[:2] == (3, 13),
        "sqlite_3_35_or_newer": sqlite3.sqlite_version_info >= (3, 35, 0),
        "locked_streamlit": streamlit_version == "1.66.0",
        "original_data_matches": sources["passed"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "streamlit": streamlit_version,
            "platform": platform.platform(),
        },
        "raw_dir": str(raw_dir),
        "data_dir": str(data_dir),
        "free_disk_bytes": free_bytes,
        "warnings": ["Allow at least 5 GB free for a full rebuild and temporary databases."]
        if free_bytes < 5 * 1024**3
        else [],
        "sources": sources,
    }
