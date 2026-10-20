"""Do offline tests for specified downloads, file publication, and exact byte conversion."""

import hashlib
import json
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from amlens.operations import download as download_module
from amlens.operations.download import download_sources

NAMES = ("HI-Small_Trans.csv", "HI-Small_accounts.csv", "HI-Small_Patterns.txt")


def checksum(contents: bytes) -> dict:
    return {"bytes": len(contents), "sha256": hashlib.sha256(contents).hexdigest()}


class SourceDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.raw = self.workspace / "数据 raw files"
        self.manifest_path = self.workspace / "dataset.json"
        self.canonical = {
            NAMES[0]: b"transaction fixture\n",
            NAMES[1]: b"account fixture\n",
            # Keep one final LF byte in the reference file. rstrip() would remove too many bytes.
            NAMES[2]: b"BEGIN pattern\nmember\nEND pattern\n",
        }
        self.remote = {**self.canonical, NAMES[2]: self.canonical[NAMES[2]] + b"\n"}
        self.manifest = {
            "dataset": "Small offline downloader fixture",
            "files": {name: checksum(contents) for name, contents in self.canonical.items()},
            "source": {
                "provider": "kaggle",
                "handle": "fixture-owner/fixture-dataset",
                "version": 8,
                "url": "https://www.kaggle.com/datasets/fixture-owner/fixture-dataset/versions/8",
                "files": {
                    NAMES[2]: {
                        **checksum(self.remote[NAMES[2]]),
                        "normalization": "remove_one_trailing_lf",
                    }
                },
            },
        }
        self._save_manifest()
        self.calls = []
        self.raw_files_seen_during_download = []

    def _save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def _tree_files(self):
        return {
            str(path.relative_to(self.workspace)): path.read_bytes()
            for path in self.workspace.rglob("*")
            if path.is_file()
        }

    def _fake_download(self, handle, *, path, output_dir, force_download):
        self.calls.append(
            {
                "handle": handle,
                "path": path,
                "output_dir": output_dir,
                "force_download": force_download,
            }
        )
        self.raw_files_seen_during_download.append(
            {item.name for item in self.raw.iterdir() if item.is_file()}
            if self.raw.exists()
            else set()
        )
        output = Path(output_dir) / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(self.remote[path])
        return str(output)

    def _download(self, download_file=None, **kwargs):
        return download_sources(
            self.raw,
            manifest_path=self.manifest_path,
            download_file=download_file or self._fake_download,
            **kwargs,
        )

    def _existing(self, name):
        self.raw.mkdir(exist_ok=True)
        (self.raw / name).write_bytes(self.canonical[name])

    def test_downloads_only_three_pinned_files_and_publishes_canonical_bytes(self):
        report = self._download()
        self.assertIsInstance(report, dict)
        self.assertEqual({call["path"] for call in self.calls}, set(NAMES))
        self.assertEqual(len(self.calls), 3)
        for call in self.calls:
            self.assertEqual(call["handle"], "fixture-owner/fixture-dataset/versions/8")
            self.assertTrue(call["force_download"])
            self.assertIsInstance(call["output_dir"], str)
            self.assertNotEqual(Path(call["output_dir"]).resolve(), self.raw.resolve())
        self.assertTrue(all(not files for files in self.raw_files_seen_during_download))
        for name, expected in self.canonical.items():
            self.assertEqual((self.raw / name).read_bytes(), expected)
        self.assertEqual(
            set(self._tree_files()),
            {"dataset.json", *(str(Path(self.raw.name) / name) for name in NAMES)},
        )

    def test_all_valid_existing_files_skip_downloads_offline(self):
        for name in NAMES:
            self._existing(name)
        before = self._tree_files()
        downloader = Mock(side_effect=AssertionError("Network must not be used"))
        self.assertIsInstance(self._download(downloader), dict)
        downloader.assert_not_called()
        self.assertEqual(self._tree_files(), before)

    def test_existing_mismatch_fails_before_any_network_and_does_not_overwrite(self):
        # Make a later manifest entry invalid. Validate all entries before downloads or file publication.
        self.raw.mkdir()
        (self.raw / NAMES[2]).write_bytes(b"user's existing evidence\n")
        before = self._tree_files()
        downloader = Mock(side_effect=AssertionError("Network must not be used"))
        with self.assertRaises((ValueError, RuntimeError, FileExistsError)) as caught:
            self._download(downloader)
        self.assertIn(NAMES[2], str(caught.exception))
        downloader.assert_not_called()
        self.assertEqual(self._tree_files(), before)

    def test_only_missing_file_is_downloaded_and_valid_existing_files_are_preserved(self):
        for name in NAMES[:2]:
            self._existing(name)
        self._download()
        self.assertEqual([call["path"] for call in self.calls], [NAMES[2]])
        for name in NAMES:
            self.assertEqual((self.raw / name).read_bytes(), self.canonical[name])

    def test_late_corruption_publishes_nothing_and_removes_staging_files(self):
        def corrupt_final_download(handle, *, path, output_dir, force_download):
            if len(self.calls) == 2:
                self.remote[path] = b"corrupt final payload"
            return self._fake_download(
                handle, path=path, output_dir=output_dir, force_download=force_download
            )

        before = self._tree_files()
        with self.assertRaises((ValueError, RuntimeError)) as caught:
            self._download(corrupt_final_download)
        self.assertIn(self.calls[-1]["path"], str(caught.exception))
        self.assertEqual({call["path"] for call in self.calls}, set(NAMES))
        self.assertTrue(all(not files for files in self.raw_files_seen_during_download))
        self.assertEqual(self._tree_files(), before)

    def test_wrong_same_size_and_truncated_payloads_are_rejected_without_partials(self):
        original = self.remote[NAMES[0]]
        for payload in [b"X" + original[1:], original[:-1]]:
            with self.subTest(payload=payload):
                self.remote[NAMES[0]] = payload
                before = self._tree_files()
                with self.assertRaises((ValueError, RuntimeError)) as caught:
                    self._download()
                self.assertIn(NAMES[0], str(caught.exception))
                self.assertEqual(self._tree_files(), before)

    def test_pattern_source_hash_is_checked_even_when_normalized_bytes_would_match(self):
        self.manifest["source"]["files"][NAMES[2]]["sha256"] = "0" * 64
        self._save_manifest()
        before = self._tree_files()
        with self.assertRaises((ValueError, RuntimeError)) as caught:
            self._download()
        self.assertIn(NAMES[2], str(caught.exception))
        self.assertEqual(self._tree_files(), before)

    def test_pattern_target_hash_is_checked_after_source_verification(self):
        self.manifest["files"][NAMES[2]]["sha256"] = "0" * 64
        self._save_manifest()
        before = self._tree_files()
        with self.assertRaises((ValueError, RuntimeError)) as caught:
            self._download()
        self.assertIn(NAMES[2], str(caught.exception))
        self.assertEqual(self._tree_files(), before)

    def test_missing_trailing_lf_is_rejected_even_with_valid_declared_source_hash(self):
        payload = self.canonical[NAMES[2]].removesuffix(b"\n")
        self.remote[NAMES[2]] = payload
        self.manifest["source"]["files"][NAMES[2]].update(checksum(payload))
        self._save_manifest()
        before = self._tree_files()
        with self.assertRaises((ValueError, RuntimeError)) as caught:
            self._download()
        self.assertIn(NAMES[2], str(caught.exception))
        self.assertEqual(self._tree_files(), before)

    def test_failed_missing_download_keeps_valid_existing_files(self):
        self._existing(NAMES[0])
        self.remote[NAMES[2]] = b"bad late file"
        before = self._tree_files()
        with self.assertRaises((ValueError, RuntimeError)):
            self._download()
        self.assertEqual(self._tree_files(), before)
        self.assertTrue(all(files == {NAMES[0]} for files in self.raw_files_seen_during_download))

    def test_reused_input_changed_during_download_blocks_publication(self):
        self._existing(NAMES[0])
        changed = b"X" + self.canonical[NAMES[0]][1:]
        expected_files = self._tree_files()
        expected_files[str(Path(self.raw.name) / NAMES[0])] = changed

        def change_existing_input(handle, *, path, output_dir, force_download):
            (self.raw / NAMES[0]).write_bytes(changed)
            return self._fake_download(
                handle, path=path, output_dir=output_dir, force_download=force_download
            )

        with self.assertRaisesRegex(ValueError, "Input changed during download") as caught:
            self._download(change_existing_input)
        self.assertIn(NAMES[0], str(caught.exception))
        self.assertTrue(self.calls)
        # Keep the caller's changed source file unchanged.
        self.assertEqual(self._tree_files(), expected_files)
        self.assertEqual((self.raw / NAMES[0]).read_bytes(), changed)

    def test_early_staged_input_changed_during_later_download_blocks_publication(self):
        before = self._tree_files()
        modified_name = []

        def change_earlier_staged_input(handle, *, path, output_dir, force_download):
            if self.calls and not modified_name:
                previous = self.calls[0]
                earlier = Path(previous["output_dir"]) / previous["path"]
                contents = earlier.read_bytes()
                earlier.write_bytes(b"X" + contents[1:])
                modified_name.append(previous["path"])
            return self._fake_download(
                handle, path=path, output_dir=output_dir, force_download=force_download
            )

        with self.assertRaisesRegex(ValueError, "Input changed during download") as caught:
            self._download(change_earlier_staged_input)
        self.assertEqual(len(modified_name), 1)
        self.assertIn(modified_name[0], str(caught.exception))
        self.assertTrue(all(not files for files in self.raw_files_seen_during_download))
        self.assertEqual(self._tree_files(), before)

    def test_corrupted_published_destination_cannot_be_reported_as_success(self):
        publish_file = download_module._publish_file
        modified_name = []

        def corrupt_published_destination(source, target):
            publish_file(source, target)
            if not modified_name:
                contents = target.read_bytes()
                target.write_bytes(b"X" + contents[1:])
                modified_name.append(target.name)

        with patch.object(
            download_module, "_publish_file", side_effect=corrupt_published_destination
        ):
            with self.assertRaisesRegex(ValueError, "size/SHA-256 mismatch") as caught:
                self._download()
        self.assertEqual(len(modified_name), 1)
        self.assertIn(modified_name[0], str(caught.exception))

    def test_network_error_is_actionable_and_does_not_leak_private_urls(self):
        private_url = "https://private-storage.invalid/download?token=private-secret-token"
        messages = []

        def fail_network(handle, *, path, output_dir, force_download):
            # Simulate a download interruption that leaves an incomplete file.
            partial = Path(output_dir) / "download.part"
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_bytes(b"partial")
            raise RuntimeError(private_url)

        before = self._tree_files()
        with self.assertRaises(RuntimeError) as caught:
            self._download(fail_network, progress=messages.append)
        message = str(caught.exception)
        self.assertRegex(message, "(?i)kaggle")
        rendered = "".join(traceback.format_exception(caught.exception)) + repr(messages)
        self.assertNotIn(private_url, rendered)
        self.assertNotIn("private-secret-token", rendered)
        self.assertEqual(self._tree_files(), before)


if __name__ == "__main__":
    unittest.main()
