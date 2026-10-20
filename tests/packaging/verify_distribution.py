"""Make sure archives contain portable source files. Exclude local data and caches."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TREES = (
    "src/amlens",
    "scripts",
    "tests",
    "reference",
    "docs",
    "static",
    ".streamlit",
    ".github",
)
REQUIRED_ROOT_FILES = (
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".gitignore",
    ".gitattributes",
    "MANIFEST.in",
    ".env.example",
    ".streamlit/config.toml",
)
EXCLUDED_PARTS = {
    ".venv",
    ".git",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "artifacts",
    "data",
    "build",
    "dist",
}


def portable_source_files(root: Path) -> set[str]:
    """List source files from the current project. Include new scripts in the required archive contents."""
    paths = set(REQUIRED_ROOT_FILES)
    for directory in SOURCE_TREES:
        for file in (root / directory).rglob("*"):
            if file.is_file() and not excluded(file.relative_to(root).as_posix()):
                paths.add(file.relative_to(root).as_posix())
    return paths


def excluded(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(set(path.parts) & EXCLUDED_PARTS) or (
        path.suffix in {".pyc", ".pyo", ".sqlite", ".db", ".duckdb", ".log"}
        or (path.name.startswith(".env") and name != ".env.example")
        or path.name.startswith(".DS_Store")
        or ".sqlite-" in path.name
    )


def verify_distributions(dist_dir: Path, root: Path = PROJECT_ROOT) -> dict[str, int]:
    source_archives = list(dist_dir.glob("*.tar.gz"))
    wheels = list(dist_dir.glob("*.whl"))
    if len(source_archives) != 1 or len(wheels) != 1:
        raise ValueError("Build exactly one sdist and one wheel into the distribution directory.")
    with tarfile.open(source_archives[0]) as archive:
        members = [member.name for member in archive.getmembers() if member.isfile()]
    if any(
        PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in members
    ):
        raise ValueError("Source distribution contains an unsafe archive path.")
    sdist_files = {PurePosixPath(*PurePosixPath(name).parts[1:]).as_posix() for name in members}
    missing = portable_source_files(root) - sdist_files
    if missing:
        raise ValueError(
            "Source distribution omitted portable files: " + ", ".join(sorted(missing))
        )
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_files = set(archive.namelist())
    runtime_files = {
        name.removeprefix("src/")
        for name in portable_source_files(root)
        if name.startswith("src/amlens/")
    }
    missing = runtime_files - wheel_files
    if missing:
        raise ValueError("Wheel omitted runtime resources: " + ", ".join(sorted(missing)))
    leaked = {name for name in sdist_files | wheel_files if excluded(name)}
    if leaked:
        raise ValueError(
            "Distribution includes local data or private artifacts: " + ", ".join(sorted(leaked))
        )
    return {"source_files": len(sdist_files), "wheel_files": len(wheel_files)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=PROJECT_ROOT / "dist")
    args = parser.parse_args()
    summary = verify_distributions(args.dist_dir)
    print(
        f"Portable distributions verified: {summary['source_files']} source files, "
        f"{summary['wheel_files']} wheel files; no raw datasets or private artifacts."
    )


if __name__ == "__main__":
    main()
