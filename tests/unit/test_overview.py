"""Verify overview evidence boundaries, snapshot lifecycle, and validated references."""

import json
import unittest
from concurrent.futures import Future
from copy import deepcopy
from unittest.mock import MagicMock, patch

from amlens.analysis.client import ModelConfig, analyze
from amlens.analysis.context import load_prompt
from amlens.analysis.overview import build_overview_context
from amlens.analysis.response import AnalysisError, validate_overview
from amlens.analysis.session import AnalysisSession
from amlens.presenters import minute_index
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import initial_state
from tests.unit.test_analysis import analysis_data


def overview_report():
    return {
        "summary": "One unreviewed case is available for inspection.",
        "findings": [
            {
                "title": "Review workload",
                "explanation": "The queue contains one pending case.",
                "metric_refs": ["pending_cases", "fan_in.active_cases"],
            }
        ],
        "focus_cases": [{"case_id": 0, "reason": "Inspect the available evidence."}],
        "next_steps": ["Check the business purpose of the transfers."],
        "limitations": ["Rule matches are not confirmed fraud."],
    }


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.data = analysis_data()
        self.state = initial_state(self.data, 0)
        self.state["cursor"] = minute_index("2022-09-01 06:00:00")
        self.session = AnalysisSession()
        self.config = ModelConfig("test-key", "test-model")
        self.prompt = load_prompt("overview_prompt.txt")
        self.futures = []
        self.calls = []

    def submit(self, *args):
        future = Future()
        future.set_running_or_notify_cancel()
        self.calls.append(args)
        self.futures.append(future)
        return future

    def start(self, identifier="overview"):
        self.session.handle_action(
            self.data,
            self.state,
            {"id": identifier, "action": "overview_insight"},
            self.config,
            load_prompt(),
            now=0,
            submit=self.submit,
            overview_prompt=self.prompt,
        )

    def snapshot(self):
        return self.session.overview_snapshot(
            self.data,
            self.state,
            self.config,
            self.prompt,
            dashboard_snapshot(self.data, self.state),
        )

    def test_context_excludes_future_versions_and_private_account_details(self):
        context = build_overview_context(self.data, self.state)
        self.assertEqual([case["evidence_id"] for case in context["cases"]], ["first"])
        self.assertEqual(context["metrics"]["detected_transactions"], 2)
        self.assertNotIn("recent_6h_transactions", context["metrics"])
        self.assertNotIn("accounts", context)
        self.assertNotIn("transactions", context)
        self.assertNotIn("review_result", context)
        for point in context["transaction_volume"]:
            self.assertLessEqual(
                minute_index(point["through"].replace("/", "-")), self.state["cursor"]
            )
        self.state["cursor"] = self.data.end
        full = build_overview_context(self.data, self.state)
        self.assertEqual([case["evidence_id"] for case in full["cases"]], ["second"])
        self.assertEqual(full["metrics"]["detected_transactions"], 3)

    def test_equal_volume_windows_use_only_observed_transactions(self):
        self.state["cursor"] = minute_index("2022-09-01 12:00:00")
        context = build_overview_context(self.data, self.state)
        self.assertEqual(context["metrics"]["recent_6h_transactions"], 2)
        self.assertEqual(context["metrics"]["previous_6h_transactions"], 6)

    def test_reviewed_cases_keep_detected_counts_but_leave_active_workload(self):
        self.state["statuses"]["0"] = {"status": "reviewed", "evidence_id": "first"}
        context = build_overview_context(self.data, self.state)
        self.assertEqual(context["metrics"]["detected_transactions"], 2)
        self.assertEqual(context["metrics"]["held_transactions"], 0)
        self.assertEqual(context["metrics"]["pending_cases"], 0)
        self.assertEqual(context["metrics"]["reviewed_cases"], 1)
        with self.assertRaises(AnalysisError):
            validate_overview(overview_report(), context)

    def test_invalid_metric_and_case_references_are_rejected(self):
        context = build_overview_context(self.data, self.state)
        self.assertEqual(validate_overview(overview_report(), context), overview_report())
        edits = [
            lambda r: r["findings"][0].update(metric_refs=["invented_metric"]),
            lambda r: r["findings"][0].update(metric_refs=[]),
            lambda r: r["focus_cases"][0].update(case_id=99),
            lambda r: r["focus_cases"][0].update(case_id=True),
        ]
        for edit in edits:
            report = overview_report()
            edit(report)
            with self.assertRaises(AnalysisError):
                validate_overview(report, context)

    def test_snapshot_survives_replay_and_review_changes_without_changing_review(self):
        self.start()
        frozen = deepcopy(self.calls[0][2])
        self.assertEqual(self.state["statuses"], {})
        self.futures[0].set_result((overview_report(), 5))
        self.session.poll(6)
        self.assertFalse(self.snapshot()["stale"])
        self.state["statuses"]["0"] = {"status": "investigating", "evidence_id": "first"}
        self.assertTrue(self.snapshot()["stale"])
        self.state["cursor"] = self.data.end
        result = self.snapshot()
        self.assertTrue(result["stale"])
        self.assertEqual(result["entry"]["report"], overview_report())
        self.assertEqual(self.calls[0][2], frozen)
        self.assertEqual(result["entry"]["metrics"]["detected_transactions"], 2)
        self.state["view"] = "detail"
        self.assertEqual(self.snapshot()["entry"]["report"], overview_report())

    def test_duplicate_and_cross_kind_requests_share_one_worker(self):
        self.start()
        self.start()
        self.start("again")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.snapshot()["notice"], "busy")
        self.state.update(view="detail", selected=0)
        self.session.handle_action(
            self.data,
            self.state,
            {"id": "case", "action": "analyze", "value": 0, "evidenceId": "first"},
            self.config,
            load_prompt(),
            now=0,
            submit=self.submit,
        )
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.state["statuses"], {})

    def test_configuration_language_and_timeout_are_isolated(self):
        self.start()
        self.state["language"] = "zh"
        self.assertIsNone(self.snapshot()["entry"])
        self.state["language"] = "en"
        self.config = ModelConfig("test-key", "another-model")
        self.assertIsNone(self.snapshot()["entry"])
        self.config = ModelConfig("test-key", "test-model")
        self.session.poll(121)
        self.assertEqual(self.snapshot()["entry"]["error"], "timeout")
        self.start("retry")
        self.futures[0].set_result((overview_report(), 122))
        self.assertEqual(self.snapshot()["entry"]["status"], "running")
        self.session.close()
        self.assertIsNone(self.snapshot()["entry"])

    def test_empty_overview_and_unconfigured_model_do_not_submit(self):
        self.state["cursor"] = self.data.start - 1
        self.start()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.snapshot()["notice"], "no_data")
        self.config = ModelConfig("", "test-model")
        self.start("unconfigured")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.snapshot()["notice"], "configuration")

    @patch("amlens.analysis.client.time.monotonic", return_value=10)
    @patch("amlens.analysis.client.urlopen")
    def test_overview_request_uses_own_schema_and_validator(self, urlopen, clock):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(overview_report()),
                        },
                    }
                ],
            }
        ).encode()
        urlopen.return_value = response
        context = build_overview_context(self.data, self.state)
        report, _ = analyze(self.config, context, self.prompt, "en", 120, "overview")
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["response_format"]["json_schema"]["name"], "amlens_overview_insight")
        self.assertIn("overview_data", json.loads(body["messages"][1]["content"]))
        self.assertEqual(report, overview_report())


if __name__ == "__main__":
    unittest.main()
