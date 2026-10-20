"""Own analysis jobs and results in one browser session, separate from replay state."""

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from amlens.analysis.client import TIMEOUT_SECONDS, ModelConfig, analyze
from amlens.analysis.context import Prompt, build_context, load_prompt
from amlens.analysis.overview import build_overview_context, overview_version
from amlens.analysis.response import AnalysisError
from amlens.services.case_service import ReplayDataset
from amlens.services.replay_service import apply_action

# Workers receive detached evidence, not session state or a Streamlit context.
_workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="amlens-analysis")


@dataclass
class Job:
    future: Future
    deadline: float
    entry: dict


class AnalysisSession:
    def __init__(self):
        self.entries = {}
        self.job: Job | None = None
        self.notice: tuple[int, str] | None = None
        self.overview_entries = {}
        self.overview_notice: str | None = None

    def poll(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        job = self.job
        if job is None:
            return
        if job.future.done():
            try:
                result, finished = job.future.result()
                if finished > job.deadline:
                    raise AnalysisError("timeout")
                job.entry.update(status="succeeded", report=result)
            except AnalysisError as error:
                job.entry.update(status="failed", error=error.code)
            except Exception:
                # Raw exceptions can contain upstream content. Keep them out of the UI.
                job.entry.update(status="failed", error="unavailable")
            self.job = None
        elif now >= job.deadline:
            job.future.cancel()
            job.entry.update(status="failed", error="timeout")
            # Late results have no path back into the session after this point.
            self.job = None
        if self.job is None and self.notice and self.notice[1] == "busy":
            self.notice = None
        if self.job is None and self.overview_notice == "busy":
            self.overview_notice = None

    def close(self) -> None:
        if self.job:
            self.job.future.cancel()
        self.job = None
        self.entries.clear()
        self.notice = None
        self.overview_entries.clear()
        self.overview_notice = None

    @staticmethod
    def cache_key(data, evidence_id, config, prompt, language):
        return (data.fingerprint, evidence_id, config.model, prompt.version, language)

    def handle_action(
        self,
        data: ReplayDataset,
        state: dict,
        packet,
        config: ModelConfig,
        prompt: Prompt,
        *,
        now: float | None = None,
        submit=None,
        overview_prompt: Prompt | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now
        self.poll(now)
        if (
            not isinstance(packet, dict)
            or not isinstance(packet.get("id"), str)
            or packet["id"] in state["seen"]
        ):
            return
        apply_action(state, data, packet, now)
        if packet.get("action") == "overview_insight":
            if state["view"] == "overview":
                self._start_overview(
                    data,
                    state,
                    config,
                    overview_prompt or load_prompt("overview_prompt.txt"),
                    now,
                    submit,
                )
            return
        if packet.get("action") != "analyze":
            return
        identifier = packet.get("value")
        if type(identifier) is not int or state["view"] != "detail":
            return
        if identifier != state["selected"]:
            return
        case = next((case for case in data.visible(state) if case.id == identifier), None)
        if case is None:
            return
        self.notice = None
        if packet.get("evidenceId") != case.evidence_id:
            self.notice = (identifier, "stale")
            return
        if self.job is not None:
            self.notice = (identifier, "busy")
            return
        if not config.configured:
            self.notice = (identifier, "configuration")
            return
        language = state["language"]
        cache_key = self.cache_key(data, case.evidence_id, config, prompt, language)
        entry = {
            "status": "running",
            "model": config.model,
            "promptVersion": prompt.version,
            "evidenceId": case.evidence_id,
            "version": case.version,
            "language": language,
        }
        try:
            context = build_context(data, case)
            future = (submit or _workers.submit)(
                analyze, config, context, prompt, language, now + TIMEOUT_SECONDS
            )
        except Exception:
            self.notice = (identifier, "unavailable")
            return
        self.entries[cache_key] = entry
        self.job = Job(future, now + TIMEOUT_SECONDS, entry)
        if data.status(case, state) != "reviewed":
            state["statuses"][str(identifier)] = {
                "status": "investigating",
                "evidence_id": case.evidence_id,
            }

    @staticmethod
    def overview_key(data, config, prompt, language):
        return (data.fingerprint, config.model, prompt.version, language)

    def _start_overview(self, data, state, config, prompt, now, submit):
        self.overview_notice = None
        if self.job is not None:
            self.overview_notice = "busy"
            return
        if not config.configured:
            self.overview_notice = "configuration"
            return
        try:
            context = build_overview_context(data, state)
            if not context["metrics"]["processed_transactions"]:
                self.overview_notice = "no_data"
                return
            entry = {
                "status": "running",
                "model": config.model,
                "promptVersion": prompt.version,
                "language": state["language"],
                "asOf": context["as_of"],
                "snapshotVersion": overview_version(context),
                "metrics": context["metrics"],
            }
            future = (submit or _workers.submit)(
                analyze,
                config,
                context,
                prompt,
                state["language"],
                now + TIMEOUT_SECONDS,
                "overview",
            )
        except Exception:
            self.overview_notice = "unavailable"
            return
        self.overview_entries[self.overview_key(data, config, prompt, state["language"])] = entry
        self.job = Job(future, now + TIMEOUT_SECONDS, entry)

    def overview_snapshot(self, data, state, config, prompt, dashboard) -> dict:
        entry = self.overview_entries.get(
            self.overview_key(data, config, prompt, state["language"])
        )
        stale = False
        if entry and state["view"] == "overview":
            current = build_overview_context(data, state, dashboard)
            stale = entry["snapshotVersion"] != overview_version(current)
        return {
            "entry": dict(entry) if entry else None,
            "stale": stale,
            "busy": self.job is not None,
            "configured": config.configured,
            "notice": self.overview_notice,
        }

    def snapshot(self, data, detail, config, prompt, language) -> dict:
        entry = None
        if detail:
            entry = self.entries.get(
                self.cache_key(data, detail["evidenceId"], config, prompt, language)
            )
        notice = (
            self.notice[1] if self.notice and detail and self.notice[0] == detail["id"] else None
        )
        return {
            "entry": dict(entry) if entry else None,
            "busy": self.job is not None,
            "configured": config.configured,
            "notice": notice,
            "features": data.analysis_evidence[detail["evidenceId"]]["features"] if detail else {},
        }
