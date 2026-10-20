"""Detect changed inputs. Keep original files unchanged during project setup."""

import hashlib
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amlens.ingestion.import_service import SOURCE_FILES
from amlens.operations.environment import check_sources

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
with patch.object(sys, "path", [str(SCRIPTS), *sys.path]):
    copy_sources = runpy.run_path(str(SCRIPTS / "reproduce.py"))["copy_sources"]


class ReproductionInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "原始 data"
        self.target = self.root / "复制 data"
        self.source.mkdir()
        files = {}
        for name in SOURCE_FILES:
            content = (name + "\n测试\n").encode()
            (self.source / name).write_bytes(content)
            files[name] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        self.manifest = self.root / "reference.json"
        self.manifest.write_text(json.dumps({"files": files}), encoding="utf-8")

    def test_same_size_mutation_and_missing_file_fail_hash_check(self):
        self.assertTrue(check_sources(self.source, self.manifest)["passed"])
        file = self.source / SOURCE_FILES[0]
        original = file.read_bytes()
        file.write_bytes(b"!" + original[1:])
        report = check_sources(self.source, self.manifest)
        self.assertFalse(report["passed"])
        self.assertTrue(report["files"][file.name]["exists"])
        file.unlink()
        self.assertFalse(check_sources(self.source, self.manifest)["files"][file.name]["exists"])

    def test_copies_originals_and_accepts_identical_existing_files(self):
        copy_sources(self.source, self.target)
        copy_sources(self.source, self.target)
        for name in SOURCE_FILES:
            self.assertEqual((self.source / name).read_bytes(), (self.target / name).read_bytes())
        self.assertTrue(check_sources(self.target, self.manifest)["passed"])

    def test_different_existing_input_is_never_overwritten(self):
        self.target.mkdir()
        existing = self.target / SOURCE_FILES[0]
        existing.write_bytes(b"another dataset")
        with self.assertRaisesRegex(ValueError, "Refusing to replace"):
            copy_sources(self.source, self.target)
        self.assertEqual(existing.read_bytes(), b"another dataset")
        self.assertTrue(check_sources(self.source, self.manifest)["passed"])

    def test_interrupted_copy_removes_its_partial_output(self):
        def fail(source, destination, length):
            destination.write(b"partial")
            raise OSError("disk full")

        with patch("shutil.copyfileobj", side_effect=fail):
            with self.assertRaisesRegex(OSError, "disk full"):
                copy_sources(self.source, self.target)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertTrue(check_sources(self.source, self.manifest)["passed"])


if __name__ == "__main__":
    unittest.main()
