"""Make sure data paths and launcher defaults work after relocation or installation."""

import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from amlens.cli import STREAMLIT_DEFAULTS, main, streamlit_command
from amlens.config import find_project_root, resolve_data_directory


class DataDirectoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "user home"
        self.module = self.root / "moved project" / "src" / "amlens" / "config.py"
        self.module.parent.mkdir(parents=True)
        (self.module.parents[2] / "pyproject.toml").write_text("[project]\nname='amlens-app'\n")
        self.installed = self.root / "environment" / "site-packages" / "amlens" / "config.py"

    def resolve(self, module=None, **kwargs):
        return resolve_data_directory(
            module or self.module,
            environment=kwargs.pop("environment", {}),
            home=self.home,
            **kwargs,
        )

    def test_checkout_data_follows_project_not_current_directory(self):
        expected = self.module.parents[2] / "data"
        self.assertEqual(find_project_root(self.module), self.module.parents[2])
        with patch("os.getcwd", return_value=str(self.root / "unrelated")):
            self.assertEqual(self.resolve(), expected)
        self.assertFalse(expected.exists())

    def test_override_is_shared_by_checkout_and_wheel_and_supports_spaces(self):
        configured = self.root / "external data"
        for module in (self.module, self.installed):
            self.assertEqual(
                self.resolve(module, environment={"AMLENS_DATA_DIR": str(configured)}),
                configured,
            )
            self.assertEqual(
                self.resolve(module, environment={"AMLENS_DATA_DIR": "~/AML data"}),
                self.home / "AML data",
            )
        with self.assertRaisesRegex(ValueError, "absolute path"):
            self.resolve(environment={"AMLENS_DATA_DIR": "relative/data"})

    def test_wheel_uses_platform_user_data_not_site_packages(self):
        self.assertIsNone(find_project_root(self.installed))
        expected = {
            "darwin": self.home / "Library" / "Application Support" / "AMLens",
            "win32": self.home / "AppData" / "Local" / "AMLens",
            "linux": self.home / ".local" / "share" / "amlens",
        }
        for platform, directory in expected.items():
            with self.subTest(platform=platform):
                self.assertEqual(self.resolve(self.installed, platform=platform), directory)
                self.assertFalse(directory.exists())

    def test_platform_environment_roots_must_also_be_absolute(self):
        custom = self.root / "custom local data"
        for platform, variable, suffix in (
            ("linux", "XDG_DATA_HOME", "amlens"),
            ("win32", "LOCALAPPDATA", "AMLens"),
        ):
            with self.subTest(platform=platform):
                self.assertEqual(
                    self.resolve(
                        self.installed, platform=platform, environment={variable: str(custom)}
                    ),
                    custom / suffix,
                )
                self.assertEqual(
                    self.resolve(
                        self.installed, platform=platform, environment={variable: "relative"}
                    ),
                    self.resolve(self.installed, platform=platform),
                )


class LauncherTests(unittest.TestCase):
    def test_defaults_match_existing_project_streamlit_configuration(self):
        root = Path(__file__).resolve().parents[2]
        configured = tomllib.loads((root / ".streamlit" / "config.toml").read_text())
        for option, expected in STREAMLIT_DEFAULTS.items():
            if option == "server.address":
                self.assertNotIn("address", configured["server"])
                self.assertEqual(expected, "127.0.0.1")
                continue
            section, key = option.split(".")
            actual = configured[section][key]
            if isinstance(actual, bool):
                actual = str(actual).lower()
            self.assertEqual(actual, expected)
        command = streamlit_command([])
        self.assertTrue(Path(command[4]).is_absolute())
        for option, value in STREAMLIT_DEFAULTS.items():
            self.assertIn(f"--{option}={value}", command)

    def test_explicit_streamlit_options_override_defaults_without_duplicates(self):
        arguments = [
            "--server.address",
            "0.0.0.0",
            "--server.headless=false",
            "--server.port=8513",
        ]
        command = streamlit_command(arguments)
        self.assertEqual(command[-len(arguments) :], arguments)
        self.assertNotIn("--server.address=127.0.0.1", command)
        self.assertNotIn("--server.headless=true", command)
        self.assertIn("--theme.backgroundColor=#F7F2EB", command)

    def test_script_arguments_after_separator_do_not_override_streamlit(self):
        command = streamlit_command(["--", "--server.headless=false"])
        self.assertIn("--server.headless=true", command)
        self.assertEqual(command[-2:], ["--", "--server.headless=false"])

    def test_launch_uses_current_python_no_shell_and_returns_child_status(self):
        with patch("amlens.cli.subprocess.call", return_value=17) as launch:
            self.assertEqual(main(["--server.port=8513"]), 17)
        launch.assert_called_once_with(streamlit_command(["--server.port=8513"]))
        self.assertEqual(launch.call_args.kwargs, {})

    def test_keyboard_interrupt_returns_conventional_exit_status(self):
        with patch("amlens.cli.subprocess.call", side_effect=KeyboardInterrupt):
            self.assertEqual(main([]), 130)


if __name__ == "__main__":
    unittest.main()
