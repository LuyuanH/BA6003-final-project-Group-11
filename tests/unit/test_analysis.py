"""Exercise evidence boundaries, asynchronous lifecycle, and the OpenRouter contract."""

import io
import json
import os
import tempfile
import unittest
from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from amlens.analysis.client import ModelConfig, analyze
from amlens.analysis.context import Prompt, build_context, load_prompt
from amlens.analysis.response import AnalysisError, validate_report
from amlens.analysis.session import AnalysisSession
from amlens.presenters import minute_index
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import initial_state
from tests.unit.test_replay import fixture_records


def sample_report():
    return {
        "summary": "资金先后经过三个账户。",
        "assessment": "insufficient_evidence",
        "reason": "没有交易目的或账户业务背景。",
        "pattern_assessment": {
            "verdict": "unsupported",
            "explanation": "所示交易为连续路径，不能证明集中收款。",
            "transaction_ids": [1, 2],
            "feature_names": [],
        },
        "supporting_evidence": [
            {
                "explanation": "相邻账户之间在短时间内转账，需核查交易目的。",
                "transaction_ids": [1, 2],
                "feature_names": ["span_hours"],
            }
        ],
        "counter_evidence": [],
        "normal_explanations": ["假设：可能是正常结算，尚无业务凭证证实。"],
        "missing_information": ["交易目的与业务凭证。"],
        "next_steps": ["核对两笔交易的业务凭证。"],
    }


def analysis_data():
    records = fixture_records()
    for row in records["evidence"]:
        row.update(
            features={"span_hours": 1, "window_hours": 48},
            explanation=[{"feature": "span_hours", "operator": "<=", "value": 12}],
            ruleset_version="test-v1",
        )
    return ReplayDataset(records)


class ModelConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="amlens 配置 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env_file = self.root / ".env"

    def read(self, environment=None):
        with (
            patch("amlens.analysis.client.find_project_root", return_value=self.root),
            patch.dict(os.environ, environment or {}, clear=True),
        ):
            config = ModelConfig.from_environment()
            self.assertEqual(dict(os.environ), environment or {})
            return config

    def test_project_dotenv_preserves_quotes_comments_and_literal_dollars(self):
        self.env_file.write_text(
            '\ufeff# local settings\nexport OPENROUTER_API_KEY="test-${LITERAL}-key"\n'
            "AMLENS_AI_MODEL='provider/model' # a comment\n",
            encoding="utf-8",
        )
        config = self.read()
        self.assertEqual(config.api_key, "test-${LITERAL}-key")
        self.assertEqual(config.model, "provider/model")
        self.assertTrue(config.configured)
        self.assertNotIn(config.api_key, repr(config))

    def test_environment_overrides_file_including_explicitly_empty_settings(self):
        self.env_file.write_text("OPENROUTER_API_KEY=file-key\nAMLENS_AI_MODEL=file-model\n")
        config = self.read({"OPENROUTER_API_KEY": "environment-key"})
        self.assertEqual(config.api_key, "environment-key")
        self.assertEqual(config.model, "file-model")
        self.assertFalse(self.read({"OPENROUTER_API_KEY": ""}).configured)

    def test_missing_empty_or_removed_file_is_not_cached(self):
        self.assertFalse(self.read().configured)
        self.env_file.write_text("OPENROUTER_API_KEY\nAMLENS_AI_MODEL=\n")
        self.assertFalse(self.read().configured)
        self.env_file.write_text("OPENROUTER_API_KEY=key\nAMLENS_AI_MODEL=model\n")
        self.assertTrue(self.read().configured)
        self.env_file.unlink()
        self.assertFalse(self.read().configured)

    def test_invalid_file_encoding_disables_ai_but_preserves_environment_settings(self):
        self.env_file.write_bytes(b"OPENROUTER_API_KEY=\xff\xfe")
        self.assertFalse(self.read().configured)
        config = self.read({"OPENROUTER_API_KEY": "env-key", "AMLENS_AI_MODEL": "env-model"})
        self.assertTrue(config.configured)
        self.assertEqual(config.model, "env-model")

    def test_uses_checkout_root_instead_of_cwd_and_data_directory_for_wheel(self):
        self.env_file.write_text("OPENROUTER_API_KEY=root-key\nAMLENS_AI_MODEL=root-model\n")
        elsewhere = self.root / "unrelated"
        elsewhere.mkdir()
        (elsewhere / ".env").write_text("OPENROUTER_API_KEY=wrong-key\nAMLENS_AI_MODEL=wrong\n")
        with patch("pathlib.Path.cwd", return_value=elsewhere):
            self.assertEqual(self.read().api_key, "root-key")
        with (
            patch("amlens.analysis.client.find_project_root", return_value=None),
            patch("amlens.analysis.client.DATA_DIR", self.root),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(ModelConfig.from_environment().api_key, "root-key")


class ContextTests(unittest.TestCase):
    def test_only_complete_evidence_and_detector_facts_are_included(self):
        records = fixture_records()
        records["evidence"][0].update(
            features={"window_hours": 48},
            decision_time="2022-09-01 06:00:00",
            is_laundering=True,
        )
        records["transactions"][0]["paid_raw"] = "0.12345678"
        records["transactions"][0]["is_laundering"] = True
        data = ReplayDataset(records)
        context = build_context(data, data.evidence[0])
        self.assertEqual([tx["id"] for tx in context["transactions"]], [1, 2])
        self.assertEqual(context["transactions"][0]["paid"], "0.12345678")
        self.assertEqual(context["feature_window_start"], "2022-08-30 06:00:00")
        self.assertNotIn("is_laundering", json.dumps(context))
        context["features"]["window_hours"] = 99
        self.assertEqual(data.analysis_evidence["first"]["features"]["window_hours"], 48)

    def test_future_feature_cutoff_rejected(self):
        data = analysis_data()
        data.analysis_evidence["first"]["decision_time"] = "2022-09-02 00:00:00"
        with self.assertRaises(ValueError):
            build_context(data, data.evidence[0])


class ReportTests(unittest.TestCase):
    def setUp(self):
        data = analysis_data()
        self.context = build_context(data, data.evidence[0])

    def test_valid_report(self):
        self.assertEqual(validate_report(sample_report(), self.context), sample_report())

    def test_bad_enum_missing_fields_and_unknown_evidence_are_rejected(self):
        edits = [
            lambda r: r.update(assessment="guilty"),
            lambda r: r.pop("summary"),
            lambda r: r.update(probability=0.98),
            lambda r: r["pattern_assessment"].update(transaction_ids=[8]),
            lambda r: r["pattern_assessment"].update(transaction_ids=[True]),
            lambda r: r["supporting_evidence"][0].update(feature_names=["unknown"]),
            lambda r: r["supporting_evidence"][0].update(transaction_ids=[], feature_names=[]),
        ]
        for edit in edits:
            report = sample_report()
            edit(report)
            with self.subTest(report=report), self.assertRaises(AnalysisError):
                validate_report(report, self.context)


class ClientTests(unittest.TestCase):
    def setUp(self):
        data = analysis_data()
        self.context = build_context(data, data.evidence[0])
        self.config = ModelConfig("test-secret", "provider/test-model")
        self.prompt = load_prompt()

    def response(self, content=None, **choice):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(content or sample_report())},
                        **choice,
                    }
                ]
            }
        ).encode()
        return response

    @patch("amlens.analysis.client.time.monotonic", return_value=10)
    @patch("amlens.analysis.client.urlopen")
    def test_request_uses_backend_secret_exact_model_and_strict_schema(self, urlopen, clock):
        urlopen.return_value = self.response()
        result, finished = analyze(self.config, self.context, self.prompt, "zh", 120)
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(body["model"], "provider/test-model")
        self.assertTrue(body["provider"]["require_parameters"])
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertFalse(body["stream"])
        self.assertNotIn("test-secret", repr(self.config))
        self.assertEqual(result, sample_report())
        self.assertEqual(finished, 10)

    @patch("amlens.analysis.client.time.monotonic", return_value=10)
    @patch("amlens.analysis.client.urlopen")
    def test_errors_are_safe_and_classified(self, urlopen, clock):
        for status, code in [
            (401, "authentication"),
            (402, "credits"),
            (429, "rate_limit"),
            (413, "context_limit"),
            (404, "model_support"),
            (503, "unavailable"),
        ]:
            urlopen.side_effect = HTTPError(
                "url", status, "secret upstream message", {}, io.BytesIO(b"secret payload")
            )
            with self.subTest(status=status), self.assertRaises(AnalysisError) as caught:
                analyze(self.config, self.context, self.prompt, "en", 120)
            self.assertEqual(str(caught.exception), code)
        for error, code in [(TimeoutError(), "timeout"), (URLError("secret"), "network")]:
            urlopen.side_effect = error
            with self.assertRaises(AnalysisError) as caught:
                analyze(self.config, self.context, self.prompt, "en", 120)
            self.assertEqual(caught.exception.code, code)

    @patch("amlens.analysis.client.time.monotonic", return_value=10)
    @patch("amlens.analysis.client.urlopen")
    def test_truncation_and_malformed_response_fail_closed(self, urlopen, clock):
        urlopen.return_value = self.response(finish_reason="length")
        with self.assertRaises(AnalysisError):
            analyze(self.config, self.context, self.prompt, "en", 120)
        response = self.response()
        response.__enter__.return_value.read.return_value = b'{"choices":[]}'
        urlopen.return_value = response
        with self.assertRaises(AnalysisError):
            analyze(self.config, self.context, self.prompt, "en", 120)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.data = analysis_data()
        self.state = initial_state(self.data, 0)
        self.state.update(cursor=minute_index("2022-09-01 06:00:00"), selected=0, view="detail")
        self.session = AnalysisSession()
        self.config = ModelConfig("test-key", "test-model")
        self.prompt = load_prompt()
        self.futures = []
        self.calls = []

    def submit(self, *args):
        future = Future()
        future.set_running_or_notify_cancel()
        self.calls.append(args)
        self.futures.append(future)
        return future

    def start(self, identifier="start", **extra):
        self.session.handle_action(
            self.data,
            self.state,
            {"id": identifier, "action": "analyze", "value": 0, "evidenceId": "first", **extra},
            self.config,
            self.prompt,
            now=0,
            submit=self.submit,
        )

    def snapshot(self):
        detail = dashboard_snapshot(self.data, self.state)["detail"]
        return self.session.snapshot(
            self.data, detail, self.config, self.prompt, self.state["language"]
        )

    def test_duplicate_and_concurrent_clicks_submit_once(self):
        self.start()
        self.start()
        self.start("second-click")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.state["statuses"]["0"]["status"], "investigating")
        self.assertEqual(self.snapshot()["entry"]["status"], "running")
        self.assertNotIn("test-key", json.dumps(self.snapshot()))

    def test_configuration_and_stale_evidence_leave_review_unchanged(self):
        self.config = ModelConfig("", "test-model")
        self.start()
        self.assertEqual(self.state["statuses"], {})
        self.assertEqual(self.snapshot()["notice"], "configuration")
        self.config = ModelConfig("key", "test-model")
        self.state["cursor"] = self.data.end
        self.start("old-evidence")
        self.assertEqual(self.state["statuses"], {})
        self.assertEqual(self.snapshot()["notice"], "stale")
        self.assertEqual(self.calls, [])

    def test_result_survives_navigation_without_completing_review(self):
        self.start()
        self.state["view"] = "overview"
        self.futures[0].set_result((sample_report(), 5))
        self.session.poll(6)
        self.state["view"] = "detail"
        self.assertEqual(self.snapshot()["entry"]["report"], sample_report())
        self.assertEqual(self.state["statuses"]["0"]["status"], "investigating")
        self.state["cursor"] = self.data.end
        self.assertIsNone(self.snapshot()["entry"])

    def test_queued_start_rejects_case_switch_and_cannot_select_future_case(self):
        self.state["selected"] = 1
        self.start()
        self.assertEqual(self.calls, [])
        self.state.update(selected=0, cursor=self.data.start)
        self.start("future")
        self.assertEqual(self.calls, [])

    def test_worker_input_is_frozen_and_language_model_prompt_isolate_cache(self):
        self.start()
        captured_context = deepcopy(self.calls[0][2])
        self.state.update(cursor=self.data.end, language="zh")
        self.futures[0].set_result((sample_report(), 4))
        self.session.poll(5)
        self.assertEqual(self.calls[0][2], captured_context)
        self.assertIsNone(self.snapshot()["entry"])
        self.state["cursor"] = minute_index("2022-09-01 06:00:00")
        self.assertIsNone(self.snapshot()["entry"])
        self.state["language"] = "en"
        self.assertIsNotNone(self.snapshot()["entry"])
        self.config = ModelConfig("key", "different-model")
        self.assertIsNone(self.snapshot()["entry"])
        self.config = ModelConfig("key", "test-model")
        self.prompt = Prompt(self.prompt.text + "updated", "updated-prompt")
        self.assertIsNone(self.snapshot()["entry"])

    def test_timeout_and_late_completion_do_not_overwrite_retry(self):
        self.start()
        self.session.poll(121)
        self.assertEqual(self.snapshot()["entry"]["error"], "timeout")
        self.futures[0].set_result((sample_report(), 122))
        self.start("retry")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.snapshot()["entry"]["status"], "running")
        self.futures[1].set_result((sample_report(), 1))
        self.session.poll(2)
        self.assertEqual(self.snapshot()["entry"]["status"], "succeeded")

    def test_late_finished_future_is_not_success_and_failure_allows_retry(self):
        self.start()
        self.futures[0].set_result((sample_report(), 125))
        self.session.poll(126)
        self.assertEqual(self.snapshot()["entry"]["error"], "timeout")
        self.start("retry")
        self.futures[1].set_exception(AnalysisError("rate_limit"))
        self.session.poll(1)
        self.assertEqual(self.snapshot()["entry"]["error"], "rate_limit")

    def test_new_session_and_dataset_reset_drop_results(self):
        self.start()
        self.futures[0].set_result((sample_report(), 1))
        self.session.poll(2)
        self.assertTrue(self.session.entries)
        other = AnalysisSession()
        self.assertFalse(other.entries)
        self.session.close()
        self.assertFalse(self.session.entries)
        self.assertIsNone(self.session.job)

    def test_analysis_does_not_reopen_completed_review(self):
        self.state["statuses"]["0"] = {"status": "reviewed", "evidence_id": "first"}
        self.start()
        self.futures[0].set_result((sample_report(), 1))
        self.session.poll(2)
        self.assertEqual(self.state["statuses"]["0"]["status"], "reviewed")


if __name__ == "__main__":
    unittest.main()
