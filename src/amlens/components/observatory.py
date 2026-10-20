"""Connect the dashboard to the Python replay session."""

from importlib.resources import files

import streamlit as st

from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import apply_action, initial_state

_assets = files("amlens.components").joinpath("dashboard")
_component = st.components.v2.component(
    "amlens_observatory",
    html=_assets.joinpath("index.html").read_text(encoding="utf-8"),
    css=_assets.joinpath("styles.css").read_text(encoding="utf-8"),
    js="\n".join(
        _assets.joinpath(name).read_text(encoding="utf-8")
        for name in ("echarts.min.js", "i18n.js", "script.js")
    ),
    isolate_styles=True,
)


def render_observatory(data: ReplayDataset, key: str = "amlens_observatory") -> None:
    state_key = key + "__state"
    dataset_key = key + "__dataset"
    component_key = key + "-" + data.fingerprint[:16]
    previous_fingerprint = st.session_state.get(dataset_key)
    if state_key not in st.session_state or previous_fingerprint != data.fingerprint:
        if previous_fingerprint:
            st.session_state.pop(key + "-" + previous_fingerprint[:16], None)
        st.session_state[state_key] = initial_state(data)
        st.session_state[dataset_key] = data.fingerprint

    def handle_action() -> None:
        apply_action(
            st.session_state[state_key], data, st.session_state.get(component_key, {}).get("action")
        )

    _component(
        key=component_key,
        data=dashboard_snapshot(data, st.session_state[state_key]),
        on_action_change=handle_action,
        height="content",
    )
