"""Apply the same page layout to local and cloud entry points."""

import streamlit as st


def configure_page() -> None:
    st.set_page_config(
        page_title="AMLens", page_icon="◈", layout="wide", initial_sidebar_state="collapsed"
    )
    st.html("""<style>
[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:#F7F2EB}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stStatusWidget"]{display:none}
.stMainBlockContainer{padding:0 24px 0!important;max-width:1600px!important}
[data-testid="stVerticalBlock"]{gap:0}footer{display:none}
</style>""")
