"""Make sure portable archives contain all required files from one validated snapshot."""

import errno
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from amlens.ingestion.import_service import SOURCE_FILES
from amlens.operations.bundle import (
    MANIFEST_NAME,
    REQUIRED_PROJECT_FILES,
    RESULT_FILES,
    create_bundle,
    project_bundle_files,
    snapshot_bundle_files,
    verify_bundle,
)


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "source checkout"
        self.data = self.root / "external data"
        self.output = self.root / "portable.zip"
        for relative in REQUIRED_PROJECT_FILES:
            self.write(self.project / relative, f"fixture for {relative}\n")
        for name in SOURCE_FILES:
            self.write(self.data / "raw" / name, f"raw fixture {name}\n")
        for name in RESULT_FILES:
            self.write(self.data / "processed" / name, f"result fixture {name}\n")

    @staticmethod
    def write(path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def bundle(self, **kwargs):
        return create_bundle(self.project, self.data, self.output, **kwargs)

    def test_archive_and_relocated_folder_verify_without_original_paths(self):
        # Make sure the bundle excludes files that belong to the local environment.
        self.write(self.project / ".venv" / "private-file", "local environment")
        self.write(self.project / ".env", "OPENROUTER_API_KEY=private-key")
        self.write(self.project / "src" / ".env.local", "OPENROUTER_API_KEY=private-key")
        self.write(self.project / "src" / "amlens" / "__pycache__" / "cache.pyc", "cache")
        report = self.bundle()
        self.assertTrue(report["includes_results"])
        self.assertTrue(verify_bundle(self.output)["passed"])
        relocated = self.root / "another computer"
        with zipfile.ZipFile(self.output) as archive:
            self.assertFalse(
                any(".venv" in name or "__pycache__" in name for name in archive.namelist())
            )
            self.assertIn("amlens-app/.env.example", archive.namelist())
            self.assertNotIn("amlens-app/.env", archive.namelist())
            self.assertNotIn("amlens-app/src/.env.local", archive.namelist())
            archive.extractall(relocated)
        extracted = relocated / "amlens-app"
        self.assertTrue(verify_bundle(extracted)["passed"])
        manifest = json.loads((extracted / MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertIn("data/raw/HI-Small_Trans.csv", manifest["files"])
        self.assertIn("data/processed/detection.sqlite", manifest["files"])

    def test_missing_project_entrypoint_prevents_export(self):
        (self.project / "scripts" / "reproduce.py").unlink()
        with self.assertRaisesRegex(ValueError, "scripts/reproduce.py"):
            self.bundle()
        self.assertFalse(self.output.exists())

    def test_missing_ai_runtime_files_prevent_export(self):
        for relative in (
            "src/amlens/analysis/client.py",
            "src/amlens/analysis/overview.py",
            "src/amlens/analysis/prompt.txt",
            "src/amlens/analysis/overview_prompt.txt",
            "src/amlens/components/dashboard/analysis.js",
        ):
            path = self.project / relative
            self.write(path, "runtime fixture")
            path.unlink()
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, relative):
                project_bundle_files(self.project, self.data)
            self.write(path, "runtime fixture")

    def test_all_raw_files_and_both_result_databases_are_required(self):
        for relative in (
            "raw/HI-Small_Trans.csv",
            "raw/HI-Small_accounts.csv",
            "raw/HI-Small_Patterns.txt",
            "processed/amlens.sqlite",
            "processed/detection.sqlite",
        ):
            path = self.data / relative
            saved = path.read_bytes()
            path.unlink()
            with self.subTest(relative=relative), self.assertRaises(FileNotFoundError):
                self.bundle()
            path.write_bytes(saved)
            self.assertFalse(self.output.exists())

    def test_result_free_bundle_still_contains_every_reproduction_input(self):
        for name in RESULT_FILES:
            (self.data / "processed" / name).unlink()
        self.bundle(include_results=False)
        self.assertTrue(verify_bundle(self.output)["passed"])
        with zipfile.ZipFile(self.output) as archive:
            manifest = json.loads(archive.read(f"amlens-app/{MANIFEST_NAME}"))
        self.assertFalse(manifest["includes_results"])
        self.assertNotIn("data/processed/detection.sqlite", manifest["files"])
        self.assertTrue(REQUIRED_PROJECT_FILES <= manifest["files"].keys())

    def test_change_between_prevalidation_and_export_is_rejected(self):
        planned = project_bundle_files(self.project, self.data)
        identities = snapshot_bundle_files(planned)
        self.write(self.data / "processed" / "amlens.sqlite", "different observations")
        with self.assertRaisesRegex(ValueError, "changed after validation"):
            self.bundle(expected_identities=identities)
        self.assertFalse(self.output.exists())

    def test_file_modified_after_its_own_archive_read_is_rejected(self):
        original_open = zipfile.ZipFile.open
        changed = False

        def open_with_change(archive, name, *args, **kwargs):
            nonlocal changed
            if isinstance(name, str) and name == "amlens-app/data/raw/HI-Small_Trans.csv":
                self.write(self.project / "README.md", "changed after README was archived")
                changed = True
            return original_open(archive, name, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "open", open_with_change):
            with self.assertRaisesRegex(ValueError, "changed after validation"):
                self.bundle()
        self.assertTrue(changed)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".bundle-*")), [])

    def test_existing_output_and_concurrent_output_are_never_replaced(self):
        self.output.write_bytes(b"keep this")
        with self.assertRaises(FileExistsError):
            self.bundle()
        self.assertEqual(self.output.read_bytes(), b"keep this")
        self.output.unlink()
        original_open = zipfile.ZipFile.open

        def open_with_output(archive, name, *args, **kwargs):
            if not self.output.exists():
                self.output.write_bytes(b"created concurrently")
            return original_open(archive, name, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "open", open_with_output):
            with self.assertRaises(FileExistsError):
                self.bundle()
        self.assertEqual(self.output.read_bytes(), b"created concurrently")
        self.assertEqual(list(self.root.glob(".bundle-*")), [])

    def test_unsupported_hard_links_fall_back_to_exclusive_copy(self):
        with patch("amlens.operations.bundle.os.link", side_effect=OSError(errno.ENOTSUP, "exFAT")):
            report = self.bundle()
        self.assertFalse(report["atomic_publication"])
        self.assertTrue(verify_bundle(self.output)["passed"])
        self.assertEqual(list(self.root.glob(".bundle-*")), [])

    def test_copy_fallback_preserves_a_concurrently_created_destination(self):
        def unavailable_link(*args):
            self.output.write_bytes(b"concurrent output")
            raise OSError(errno.ENOTSUP, "exFAT")

        with patch("amlens.operations.bundle.os.link", side_effect=unavailable_link):
            with self.assertRaises(FileExistsError):
                self.bundle()
        self.assertEqual(self.output.read_bytes(), b"concurrent output")
        self.assertEqual(list(self.root.glob(".bundle-*")), [])

    def test_failed_copy_fallback_removes_only_its_partial_output(self):
        def failed_copy(source, destination, length):
            destination.write(b"partial archive")
            raise OSError("simulated full disk")

        with (
            patch("amlens.operations.bundle.os.link", side_effect=OSError(errno.ENOTSUP, "exFAT")),
            patch("amlens.operations.bundle.shutil.copyfileobj", side_effect=failed_copy),
        ):
            with self.assertRaisesRegex(OSError, "simulated full disk"):
                self.bundle()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".bundle-*")), [])

    def test_modified_file_fails_directory_verification(self):
        self.bundle()
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(self.root / "extracted")
        extracted = self.root / "extracted" / "amlens-app"
        self.write(extracted / "README.md", "tampered content")
        report = verify_bundle(extracted)
        self.assertFalse(report["passed"])
        self.assertIn("Changed file: README.md", report["failures"])

    def test_manifest_cannot_hide_missing_runtime_files(self):
        self.bundle()
        for relative in (
            "data/processed/detection.sqlite",
            "scripts/reproduce.py",
            "src/amlens/analysis/overview_prompt.txt",
            "src/amlens/analysis/session.py",
            "src/amlens/components/dashboard/analysis.js",
        ):
            extracted = self.root / relative.replace("/", "_")
            with zipfile.ZipFile(self.output) as archive:
                archive.extractall(extracted)
            folder = extracted / "amlens-app"
            manifest_path = folder / MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["files"][relative]
            (folder / relative).unlink()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with (
                self.subTest(relative=relative),
                self.assertRaisesRegex(ValueError, "omits required"),
            ):
                verify_bundle(folder)


if __name__ == "__main__":
    unittest.main()
