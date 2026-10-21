"""Display saved SQLite detection results in the local dashboard."""

import sqlite3

import streamlit as st

from amlens.components.observatory import render_observatory
from amlens.components.page import configure_page
from amlens.config import OBSERVATION_DB, RESULTS_DB
from amlens.services.dashboard_service import load_dashboard_data

configure_page()
if not OBSERVATION_DB.exists() or not RESULTS_DB.exists():
    st.error("Prepare the source database and offline detection results before starting replay.")
    st.code("uv run python scripts/prepare_data.py\nuv run python scripts/detect_patterns.py")
    st.stop()
try:
    data = load_dashboard_data(
        str(OBSERVATION_DB),
        str(RESULTS_DB),
        OBSERVATION_DB.stat().st_mtime_ns,
        RESULTS_DB.stat().st_mtime_ns,
    )
except (ValueError, sqlite3.DatabaseError) as error:
    st.error(str(error))
    st.code("uv run python scripts/prepare_data.py\nuv run python scripts/detect_patterns.py")
    st.stop()
render_observatory(data)
