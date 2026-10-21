"""Run the cloud dashboard from the committed replay snapshot."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Also support Streamlit runners that install dependencies without the local package.
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    import streamlit as st

    from amlens.components.observatory import render_observatory
    from amlens.components.page import configure_page
    from amlens.services.snapshot_service import load_replay_snapshot

    configure_page()
    snapshot = ROOT / "deployment" / "replay.json.gz"
    try:
        status = snapshot.stat()
        data = load_replay_snapshot(str(snapshot), status.st_mtime_ns, status.st_size)
    except (OSError, ValueError):
        st.error("Replay data is unavailable. Export and commit deployment/replay.json.gz.")
        st.code("uv run --frozen python scripts/export_replay.py")
        st.stop()
    render_observatory(data)


if __name__ == "__main__":
    main()
