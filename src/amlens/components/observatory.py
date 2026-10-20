"""Connect the dashboard to the Python replay session."""

from importlib.resources import files

import streamlit as st

from amlens.analysis.client import ModelConfig
from amlens.analysis.context import load_prompt
from amlens.analysis.session import AnalysisSession
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import initial_state

_assets = files("amlens.components").joinpath("dashboard")
_component = st.components.v2.component(
    "amlens_observatory",
    html=_assets.joinpath("index.html").read_text(encoding="utf-8"),
    css=_assets.joinpath("styles.css").read_text(encoding="utf-8"),
    js="\n".join(
        _assets.joinpath(name).read_text(encoding="utf-8")
        for name in ("echarts.min.js", "i18n.js", "analysis.js", "script.js")
    ),
    isolate_styles=True,
)


def render_observatory(data: ReplayDataset, key: str = "amlens_observatory") -> None:
    state_key = key + "__state"
    dataset_key = key + "__dataset"
    analysis_key = key + "__analysis"
    component_key = key + "-" + data.fingerprint[:16]
    previous_fingerprint = st.session_state.get(dataset_key)
    if state_key not in st.session_state or previous_fingerprint != data.fingerprint:
        if previous_fingerprint:
            st.session_state.pop(key + "-" + previous_fingerprint[:16], None)
        st.session_state[state_key] = initial_state(data)
        st.session_state[dataset_key] = data.fingerprint
        previous_analysis = st.session_state.pop(analysis_key, None)
        if previous_analysis:
            previous_analysis.close()
    if analysis_key not in st.session_state:
        st.session_state[analysis_key] = AnalysisSession()
    analysis = st.session_state[analysis_key]
    config, prompt = ModelConfig.from_environment(), load_prompt()
    overview_prompt = load_prompt("overview_prompt.txt")
    analysis.poll()

    def handle_action() -> None:
        analysis.handle_action(
            data,
            st.session_state[state_key],
            st.session_state.get(component_key, {}).get("action"),
            config,
            prompt,
            overview_prompt=overview_prompt,
        )

    snapshot = dashboard_snapshot(data, st.session_state[state_key])
    snapshot["analysis"] = analysis.snapshot(
        data, snapshot["detail"], config, prompt, st.session_state[state_key]["language"]
    )
    snapshot["insight"] = analysis.overview_snapshot(
        data, st.session_state[state_key], config, overview_prompt, snapshot
    )
    _component(
        key=component_key,
        data=snapshot,
        on_action_change=handle_action,
        height="content",
    )
