"""Download the specified HI-Small files. Validate the download and local file contents."""

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from amlens.config import RAW_DIR
from amlens.ingestion.import_service import SOURCE_FILES, source_sha256
from amlens.operations.environment import DATASET_MANIFEST


def _matches(path: Path, specification: dict) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and path.stat().st_size == specification["bytes"]
        and source_sha256(path) == specification["sha256"]
    )


def _publish_file(source: Path, target: Path) -> None:
    """Keep existing inputs unchanged. If a copy fails, remove only the file that this call created."""
    owned = None
    try:
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            status = os.fstat(outgoing.fileno())
            owned = status.st_dev, status.st_ino
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except BaseException:
        if owned is not None and target.exists():
            status = target.stat()
            if owned == (status.st_dev, status.st_ino):
                target.unlink()
        raise


def download_sources(
    raw_dir: Path = RAW_DIR,
    *,
    manifest_path: Path = DATASET_MANIFEST,
    download_file: Callable | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Reuse validated files. Download missing files to a temporary directory. Publish files only after validation.

    Read the dataset version and SHA-256 values from the project manifest.
    If an existing file has different contents, stop the operation.
    Do not replace the different file.
    """
    raw_dir = Path(raw_dir).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest["files"]
    source = manifest["source"]
    if (
        source.get("provider") != "kaggle"
        or len(source.get("handle", "").split("/")) != 2
        or type(source.get("version")) is not int
        or source["version"] < 1
        or set(expected) != set(SOURCE_FILES)
    ):
        raise ValueError(
            "The download manifest must pin one Kaggle version and all three HI files."
        )
    handle = f"{source['handle']}/versions/{source['version']}"
    progress = progress or (lambda message: None)
    missing, reused = [], []
    for name, specification in expected.items():
        path = raw_dir / name
        if path.exists() or path.is_symlink():
            if not _matches(path, specification):
                raise ValueError(
                    f"Existing file differs from the frozen input: {name}. "
                    "Move it aside or choose an empty --raw-dir; no input was overwritten."
                )
            reused.append(name)
            progress(f"Verified existing {name}")
        else:
            missing.append(name)
    if missing:
        if download_file is None:
            # Import the SDK only when a download is necessary.
            from kagglehub import dataset_download

            download_file = dataset_download
        raw_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".raw-download-", dir=raw_dir.parent) as temporary:
            staging = Path(temporary).resolve()
            ready = {}
            for name in missing:
                progress(f"Downloading {name} from Kaggle version {source['version']}")
                try:
                    downloaded = download_file(
                        handle, path=name, output_dir=str(staging), force_download=True
                    )
                except Exception as error:
                    # SDK errors can contain signed URLs.
                    # Give recovery instructions without URLs, credential paths, or tokens.
                    raise RuntimeError(
                        f"Kaggle download failed for {name} ({type(error).__name__}). "
                        "Check network access and retry. If Kaggle requires authentication, "
                        "configure KAGGLE_API_TOKEN or ~/.kaggle/kaggle.json locally. "
                        "The dataset/version and checksums will not be changed automatically."
                    ) from None
                path = Path(downloaded).resolve()
                if not path.is_relative_to(staging) or path.name != name:
                    raise ValueError(f"Unexpected download path for {name}; no inputs published.")
                upstream = source.get("files", {}).get(name, expected[name])
                if not _matches(path, upstream):
                    raise ValueError(
                        f"Upstream size/SHA-256 mismatch for {name}; download rejected."
                    )
                normalization = upstream.get("normalization")
                if normalization == "remove_one_trailing_lf":
                    # Version 8 adds one final LF byte to the original Patterns file.
                    # The manifest specifies hashes before and after conversion.
                    with path.open("r+b") as stream:
                        stream.seek(-1, os.SEEK_END)
                        if stream.read(1) != b"\n":
                            raise ValueError(f"Expected one trailing LF in {name}.")
                        stream.truncate(upstream["bytes"] - 1)
                elif normalization is not None:
                    raise ValueError(f"Unsupported normalization for {name}: {normalization}")
                if not _matches(path, expected[name]):
                    raise ValueError(f"Frozen size/SHA-256 mismatch for {name}; download rejected.")
                ready[name] = path
                progress(f"Verified {name}")
            # A later download can change an earlier temporary or reused input.
            for name, specification in expected.items():
                if not _matches(ready.get(name, raw_dir / name), specification):
                    raise ValueError(f"Input changed during download: {name}; no inputs published.")
            # Publish new source files only after all downloads pass validation.
            raw_dir.mkdir(parents=True, exist_ok=True)
            for name, path in ready.items():
                _publish_file(path, raw_dir / name)
    for name, specification in expected.items():
        if not _matches(raw_dir / name, specification):
            raise ValueError(f"Final size/SHA-256 mismatch for {name}; inputs are not verified.")
    return {
        "passed": True,
        "dataset": handle,
        "raw_dir": str(raw_dir),
        "downloaded": missing,
        "reused": reused,
        "sha256": {name: specification["sha256"] for name, specification in expected.items()},
    }
