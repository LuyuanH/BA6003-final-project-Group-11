"""Find the package and data directories from any working directory."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def find_project_root(module_path: Path | None = None) -> Path | None:
    """Find a source project. Do not treat site-packages as a source project."""
    module_path = (module_path or Path(__file__)).resolve()
    package = module_path.parent
    source = package.parent
    candidate = source.parent
    if (
        package.name == "amlens"
        and source.name == "src"
        and (candidate / "pyproject.toml").is_file()
    ):
        return candidate
    return None


def resolve_data_directory(
    module_path: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Select the configured data path, project data directory, or user data directory.

    AMLENS_DATA_DIR must contain an absolute path or a path under ``~/``.
    Reject relative paths to keep database selection independent of the working directory.
    This function does not create directories.
    """
    environment = os.environ if environment is None else environment
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    configured = environment.get("AMLENS_DATA_DIR")
    if configured:
        if configured == "~":
            override = home
        elif configured.startswith(("~/", "~\\")):
            override = home / configured[2:]
        else:
            override = Path(configured).expanduser()
        if not override.is_absolute():
            raise ValueError("AMLENS_DATA_DIR must be an absolute path or start with ~/.")
        return override.resolve()
    source_root = find_project_root(module_path)
    if source_root is not None:
        return source_root / "data"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "AMLens"
    if platform == "win32":
        local_data = Path(environment.get("LOCALAPPDATA", ""))
        if not local_data.is_absolute():
            local_data = home / "AppData" / "Local"
        return local_data / "AMLens"
    local_data = Path(environment.get("XDG_DATA_HOME", ""))
    if not local_data.is_absolute():
        local_data = home / ".local" / "share"
    return local_data / "amlens"


PACKAGE_DIR = Path(__file__).resolve().parent
# A wheel has a package directory. It does not have a source project directory.
# Store writable data outside site-packages.
PROJECT_ROOT = find_project_root() or PACKAGE_DIR
DATA_DIR = resolve_data_directory()
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OBSERVATION_DB = PROCESSED_DIR / "amlens.sqlite"
RESULTS_DB = PROCESSED_DIR / "detection.sqlite"
