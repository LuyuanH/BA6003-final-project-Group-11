"""Start Streamlit with the project theme from any directory."""

import subprocess
import sys
from pathlib import Path

STREAMLIT_DEFAULTS = {
    "server.address": "127.0.0.1",
    "server.headless": "true",
    "browser.gatherUsageStats": "false",
    "theme.base": "light",
    "theme.primaryColor": "#334EAC",
    "theme.backgroundColor": "#F7F2EB",
    "theme.secondaryBackgroundColor": "#D0E3FF",
    "theme.textColor": "#081F5C",
}


def streamlit_command(arguments: list[str]) -> list[str]:
    """Keep Streamlit arguments unchanged. Let explicit arguments replace the defaults."""
    option_arguments = arguments[: arguments.index("--")] if "--" in arguments else arguments
    provided = {
        argument.removeprefix("--").split("=", 1)[0]
        for argument in option_arguments
        if argument.startswith("--")
    }
    defaults = [
        f"--{key}={value}" for key, value in STREAMLIT_DEFAULTS.items() if key not in provided
    ]
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).resolve().with_name("app.py")),
        *defaults,
        *arguments,
    ]


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    try:
        return subprocess.call(streamlit_command(arguments))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
