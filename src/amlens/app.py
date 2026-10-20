"""Display saved SQLite detection results in the local dashboard."""

import sqlite3

import streamlit as st

from amlens.components.observatory import render_observatory
from amlens.config import OBSERVATION_DB, RESULTS_DB
from amlens.services.dashboard_service import load_dashboard_data

st.set_page_config(
    page_title="AMLens", page_icon="◈", layout="wide", initial_sidebar_state="collapsed"
)
st.html("""<style>
[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:#F7F2EB}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stStatusWidget"]{display:none}
.stMainBlockContainer{padding:0 24px 0!important;max-width:1600px!important}
[data-testid="stVerticalBlock"]{gap:0}footer{display:none}
</style>""")
if not OBSERVATION_DB.exists() or not RESULTS_DB.exists():
    st.error("请先准备原始数据库与离线检测结果，再开始历史检测结果回放。")
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
