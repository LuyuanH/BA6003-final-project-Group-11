"""Create and validate project archives. Exclude local virtual environments."""

import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from amlens.ingestion.import_service import SOURCE_FILES, source_sha256

MANIFEST_NAME = "bundle-manifest.json"
SOURCE_FILES_TO_COPY = (
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".gitignore",
    ".gitattributes",
    "MANIFEST.in",
)
SOURCE_DIRECTORIES = ("src", "scripts", "tests", "docs", ".streamlit", ".github")
RESULT_FILES = ("amlens.sqlite", "detection.sqlite")

# Checksums do not show whether required files are absent.
# List all files that this bundle needs for operation and reproduction.
REQUIRED_SOURCE_GROUPS = {
    "scripts": (
        "check_environment.py",
        "detect_patterns.py",
        "download_data.py",
        "export_portable.py",
        "prepare_data.py",
        "reproduce.py",
        "verify_bundle.py",
        "verify_detection.py",
    ),
    "src/amlens": ("__init__.py", "app.py", "cli.py", "config.py", "presenters.py"),
    "src/amlens/components": ("__init__.py", "observatory.py"),
    "src/amlens/components/dashboard": (
        "echarts.min.js",
        "i18n.js",
        "index.html",
        "script.js",
        "styles.css",
    ),
    "src/amlens/db": (
        "__init__.py",
        "account_repository.py",
        "candidate_queries.py",
        "connection.py",
        "detection_repository.py",
        "pattern_queries.py",
        "replay_repository.py",
        "schema.py",
        "transaction_repository.py",
    ),
    "src/amlens/db/sql": (
        "count_by_pattern.sql",
        "count_union.sql",
        "cycle.sql",
        "fan_in.sql",
        "fan_out.sql",
        "gather_scatter.sql",
        "random.sql",
        "scatter_gather.sql",
        "stack.sql",
        "window.sql",
    ),
    "src/amlens/detection": (
        "__init__.py",
        "engine.py",
        "features.py",
        "frozen_ruleset.json",
        "identity.py",
        "rules.py",
    ),
    "src/amlens/detection/detectors": (
        "__init__.py",
        "bipartite.py",
        "cycle.py",
        "fan.py",
        "gather_scatter.py",
        "path.py",
        "scatter_gather.py",
    ),
    "src/amlens/ingestion": (
        "__init__.py",
        "csv_reader.py",
        "import_service.py",
        "normalization.py",
    ),
    "src/amlens/operations": (
        "__init__.py",
        "bundle.py",
        "download.py",
        "environment.py",
        "reference_dataset.json",
    ),
    "src/amlens/services": (
        "__init__.py",
        "case_service.py",
        "dashboard_service.py",
        "detection_service.py",
        "replay_service.py",
    ),
    "tests/reference": ("expected-detection.json", "provenance.json", "README.md"),
    ".streamlit": ("config.toml",),
}
REQUIRED_PROJECT_FILES = frozenset(SOURCE_FILES_TO_COPY) | {
    f"{directory}/{name}" for directory, names in REQUIRED_SOURCE_GROUPS.items() for name in names
}


def _required_files(include_results: bool) -> set[str]:
    required = set(REQUIRED_PROJECT_FILES)
    required.update(f"data/raw/{name}" for name in SOURCE_FILES)
    if include_results:
        required.update(f"data/processed/{name}" for name in RESULT_FILES)
    return required


def _source_files(project_root: Path) -> dict[str, Path]:
    files = {}
    for name in SOURCE_FILES_TO_COPY:
        path = project_root / name
        if path.is_file():
            files[name] = path
    for directory in SOURCE_DIRECTORIES:
        for path in sorted((project_root / directory).rglob("*")):
            if any(part == "__pycache__" or part.endswith(".egg-info") for part in path.parts):
                continue
            if (
                path.suffix in (".pyc", ".pyo")
                or path.name == ".DS_Store"
                or path.name.startswith(".bundle-")
            ):
                continue
            if path.is_symlink():
                raise ValueError(f"Source symlinks must be replaced with portable files: {path}")
            if path.is_file():
                files[path.relative_to(project_root).as_posix()] = path
    return files


def project_bundle_files(
    project_root: Path, data_dir: Path, *, include_results: bool = True
) -> dict[str, Path]:
    """List all required input files before validation and export."""
    project_root, data_dir = project_root.resolve(), data_dir.resolve()
    files = _source_files(project_root)
    for name in SOURCE_FILES:
        files[f"data/raw/{name}"] = data_dir / "raw" / name
    if include_results:
        for name in RESULT_FILES:
            files[f"data/processed/{name}"] = data_dir / "processed" / name
        for name in ("amlens.manifest.json", "detection.summary.json", "reproduction-report.json"):
            path = data_dir / "processed" / name
            if path.is_file():
                files[f"data/processed/{name}"] = path
    missing = _required_files(include_results) - files.keys()
    if missing:
        raise ValueError("Required project files are missing: " + ", ".join(sorted(missing)))
    for path in files.values():
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.is_symlink():
            raise ValueError(f"Bundle inputs must be regular files: {path}")
    return files


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    status = path.stat()
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns


def snapshot_bundle_files(files: dict[str, Path]) -> dict[str, tuple[int, int, int, int, int]]:
    """Record each input file identity before source and database validation."""
    return {name: _file_identity(path) for name, path in files.items()}


def _check_snapshot(files: dict[str, Path], expected: dict) -> None:
    if files.keys() != expected.keys():
        raise ValueError("Bundle file inventory changed after validation; retry the export")
    for name, path in files.items():
        if path.is_symlink() or _file_identity(path) != expected[name]:
            raise ValueError(f"File changed after validation or during export; retry: {path}")


def _publish_bundle(temporary: Path, output: Path) -> bool:
    """Publish the archive without replacement of an existing file.

    Use a hard link for atomic publication when the filesystem permits it.
    Otherwise, create a new destination file and copy the archive contents.
    The destination contains incomplete data until the copy finishes.
    If the copy fails, remove only the file that this call created.
    """
    try:
        os.link(temporary, output)
        return True
    except FileExistsError:
        raise
    except OSError as error:
        unsupported = {
            errno.ENOTSUP,
            errno.EOPNOTSUPP,
            errno.ENOSYS,
            errno.EPERM,
            errno.EXDEV,
            errno.EINVAL,
        }
        if error.errno not in unsupported and getattr(error, "winerror", None) not in {1, 50}:
            raise
    owned_identity = None
    try:
        with temporary.open("rb") as source, output.open("xb") as destination:
            status = os.fstat(destination.fileno())
            owned_identity = status.st_dev, status.st_ino
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
    except BaseException:
        if owned_identity is not None and output.exists():
            current = output.stat()
            if (current.st_dev, current.st_ino) == owned_identity:
                output.unlink()
        raise
    return False


def create_bundle(
    project_root: Path,
    data_dir: Path,
    output: Path,
    *,
    include_results: bool = True,
    expected_identities: dict | None = None,
) -> dict:
    """Export the validated file snapshot. Use atomic publication when the filesystem permits it."""
    if output.exists():
        raise FileExistsError(f"Choose a new archive name; file already exists: {output}")
    files = project_bundle_files(project_root, data_dir, include_results=include_results)
    expected_identities = (
        snapshot_bundle_files(files) if expected_identities is None else expected_identities
    )
    _check_snapshot(files, expected_identities)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".bundle-", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "includes_results": include_results,
        "files": {},
    }
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for name, path in sorted(files.items()):
                digest = hashlib.sha256()
                size = 0
                with (
                    path.open("rb") as source,
                    archive.open(f"amlens-app/{name}", "w", force_zip64=True) as target,
                ):
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if (
                    _file_identity(path) != expected_identities[name]
                    or size != expected_identities[name][2]
                ):
                    raise ValueError(
                        f"File changed during export; retry after processing ends: {path}"
                    )
                manifest["files"][name] = {"bytes": size, "sha256": digest.hexdigest()}
            _validate_manifest(manifest)
            archive.writestr(
                f"amlens-app/{MANIFEST_NAME}",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
        # Compare all input files again after compression.
        # This comparison makes sure the archive uses the validated source and database files.
        final_files = project_bundle_files(project_root, data_dir, include_results=include_results)
        _check_snapshot(final_files, expected_identities)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        atomic_publication = _publish_bundle(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "archive": str(output),
        "archive_bytes": output.stat().st_size,
        "files": len(files),
        "includes_results": include_results,
        "atomic_publication": atomic_publication,
    }


def _validate_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        raise ValueError("Unsupported or empty bundle manifest")
    if not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ValueError("Unsupported or empty bundle manifest")
    if type(manifest.get("includes_results")) is not bool:
        raise ValueError("Bundle manifest must declare whether results are included")
    missing = _required_files(manifest["includes_results"]) - manifest["files"].keys()
    if missing:
        raise ValueError("Bundle omits required files: " + ", ".join(sorted(missing)))
    if not manifest["includes_results"] and any(
        f"data/processed/{name}" in manifest["files"] for name in RESULT_FILES
    ):
        raise ValueError("Bundle result files disagree with includes_results")
    if len({name.casefold() for name in manifest["files"]}) != len(manifest["files"]):
        raise ValueError("Bundle filenames collide on case-insensitive filesystems")
    for name, metadata in manifest["files"].items():
        if not isinstance(name, str) or not isinstance(metadata, dict):
            raise ValueError("Invalid file metadata in bundle manifest")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or ":" in name
            or path.as_posix() != name
            or name in ("", ".")
        ):
            raise ValueError(f"Invalid manifest path: {name}")
        digest = metadata.get("sha256")
        if (
            type(metadata.get("bytes")) is not int
            or metadata["bytes"] < 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"Invalid file metadata: {name}")
    return manifest["files"]


def verify_bundle(path: Path) -> dict:
    """Validate an archive or extracted project directory. Do not extract archive code."""
    failures = []
    if path.is_dir():
        manifest = json.loads((path / MANIFEST_NAME).read_text(encoding="utf-8"))
        expected = _validate_manifest(manifest)
        for name, metadata in expected.items():
            file = path / name
            if (
                not file.is_file()
                or file.is_symlink()
                or not file.resolve().is_relative_to(path.resolve())
            ):
                failures.append(f"Missing or non-regular file: {name}")
            elif (
                file.stat().st_size != metadata["bytes"]
                or source_sha256(file) != metadata["sha256"]
            ):
                failures.append(f"Changed file: {name}")
    else:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate paths in bundle")
            manifest = json.loads(archive.read(f"amlens-app/{MANIFEST_NAME}"))
            expected = _validate_manifest(manifest)
            allowed = {f"amlens-app/{name}" for name in expected} | {f"amlens-app/{MANIFEST_NAME}"}
            if set(names) != allowed:
                failures.append("Archive file list differs from its manifest")
            for name, metadata in expected.items():
                member = f"amlens-app/{name}"
                if member not in names:
                    failures.append(f"Missing file: {name}")
                    continue
                if stat.S_ISLNK(archive.getinfo(member).external_attr >> 16):
                    failures.append(f"Non-regular file: {name}")
                    continue
                digest = hashlib.sha256()
                with archive.open(member) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if (
                    archive.getinfo(member).file_size != metadata["bytes"]
                    or digest.hexdigest() != metadata["sha256"]
                ):
                    failures.append(f"Changed file: {name}")
    return {"passed": not failures, "checked_files": len(expected), "failures": failures}
