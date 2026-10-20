"""Remove one capability at a time and compare behavior with an explicit baseline.

All model work is local and mocked. These tests measure functional isolation, not
fraud-detection accuracy or the quality of a provider's generated prose.
"""

import unittest
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime
from unittest.mock import Mock, patch

from amlens.analysis.client import ModelConfig
from amlens.analysis.context import build_context, load_prompt
from amlens.analysis.overview import build_overview_context
from amlens.analysis.response import AnalysisError, validate_overview, validate_report
from amlens.analysis.session import AnalysisSession
from amlens.db.pattern_queries import select_candidates
from amlens.detection.engine import generate
from amlens.presenters import minute_index
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import apply_action, initial_state
from tests.unit import test_detection as detection_fixture
from tests.unit.test_analysis import analysis_data, sample_report
from tests.unit.test_overview import overview_report
from tests.unit.test_replay import fixture_records


class AnalysisAblationTests(unittest.TestCase):
    def setUp(self):
        self.data = analysis_data()
        self.state = initial_state(self.data, 0)
        self.state["cursor"] = minute_index("2022-09-01 06:00:00")
        self.config = ModelConfig("test-key", "test-model")

    def test_overview_disabled_failed_or_removed_leaves_replay_and_review_identical(self):
        for variant in (
            "removed",
            "unconfigured",
            "success",
            "network",
            "invalid_output",
            "timeout",
            "submit_failure",
        ):
            with self.subTest(variant=variant):
                baseline, state = deepcopy(self.state), deepcopy(self.state)
                packet = {"id": "insight", "action": "overview_insight"}
                apply_action(baseline, self.data, packet, 0)
                session, future = AnalysisSession(), Future()
                future.set_running_or_notify_cancel()
                submit = Mock(return_value=future)
                if variant == "submit_failure":
                    submit.side_effect = RuntimeError("worker unavailable")
                if variant == "removed":
                    apply_action(state, self.data, packet, 0)
                else:
                    config = ModelConfig("", "") if variant == "unconfigured" else self.config
                    session.handle_action(
                        self.data, state, packet, config, load_prompt(), now=0, submit=submit
                    )
                    if variant == "success":
                        report = validate_overview(
                            overview_report(), build_overview_context(self.data, state)
                        )
                        future.set_result((report, 1))
                        session.poll(2)
                    elif variant in ("network", "invalid_output"):
                        future.set_exception(AnalysisError(variant))
                        session.poll(2)
                    elif variant == "timeout":
                        session.poll(121)
                self.assertEqual(state, baseline)
                self.assertEqual(
                    dashboard_snapshot(self.data, state), dashboard_snapshot(self.data, baseline)
                )
                if variant in ("removed", "unconfigured"):
                    submit.assert_not_called()
                for event in (
                    {"id": "play", "action": "play"},
                    {"id": "tick", "action": "tick"},
                    {
                        "id": "review",
                        "action": "complete_review",
                        "evidenceId": "first",
                        "value": {"caseId": 0, "comment": "Checked", "fraudType": "NON_FRAUD"},
                    },
                ):
                    apply_action(baseline, self.data, event, 2)
                    session.handle_action(
                        self.data, state, event, self.config, load_prompt(), now=2, submit=submit
                    )
                    self.assertEqual(state, baseline)
                self.assertTrue(state["review_result"]["ok"])
                session.close()

    def test_case_analysis_outcomes_never_complete_or_release_a_review(self):
        for variant in ("unconfigured", "success", "network", "timeout"):
            with self.subTest(variant=variant):
                state = deepcopy(self.state)
                state.update(view="detail", selected=0)
                before = dashboard_snapshot(self.data, state)
                session, future = AnalysisSession(), Future()
                future.set_running_or_notify_cancel()
                config = ModelConfig("", "") if variant == "unconfigured" else self.config
                session.handle_action(
                    self.data,
                    state,
                    {"id": "analyze", "action": "analyze", "value": 0, "evidenceId": "first"},
                    config,
                    load_prompt(),
                    now=0,
                    submit=Mock(return_value=future),
                )
                if variant == "success":
                    future.set_result((sample_report(), 1))
                    session.poll(2)
                elif variant == "network":
                    future.set_exception(AnalysisError("network"))
                    session.poll(2)
                elif variant == "timeout":
                    session.poll(121)
                after = dashboard_snapshot(self.data, state)
                for key in ("processed", "hold", "reviewed", "patterns", "trend"):
                    self.assertEqual(after[key], before[key], key)
                self.assertIsNone(state["review_result"])
                expected = "pending" if variant == "unconfigured" else "investigating"
                self.assertEqual(after["queue"][0]["status"], expected)
                session.close()

    def test_removing_detector_features_preserves_overview_and_rejects_missing_references(self):
        baseline = build_overview_context(self.data, self.state)
        snapshot = dashboard_snapshot(self.data, self.state)
        without_features = deepcopy(self.data)
        for evidence in without_features.analysis_evidence.values():
            evidence["features"] = {}
            evidence["predicates"] = []
        self.assertEqual(build_overview_context(without_features, self.state), baseline)
        self.assertEqual(dashboard_snapshot(without_features, self.state), snapshot)
        context = build_context(without_features, without_features.evidence[0])
        with self.assertRaises(AnalysisError):
            validate_report(sample_report(), context)
        report = sample_report()
        report["supporting_evidence"][0]["feature_names"] = []
        self.assertEqual(validate_report(report, context), report)

    def test_empty_evidence_preserves_transaction_volume_and_blocks_case_references(self):
        records = fixture_records()
        records["evidence"] = []
        data = ReplayDataset(records)
        context = build_overview_context(data, self.state)
        self.assertEqual(context["metrics"]["processed_transactions"], 6)
        for metric in ("detected_transactions", "held_transactions", "observed_cases"):
            self.assertEqual(context["metrics"][metric], 0)
        self.assertEqual(context["cases"], [])
        with self.assertRaises(AnalysisError):
            validate_overview(overview_report(), context)
        report = overview_report()
        report["focus_cases"] = []
        self.assertEqual(validate_overview(report, context), report)

    def test_filters_selection_and_language_do_not_change_global_evidence(self):
        baseline = build_overview_context(self.data, self.state)
        for fields in (
            {"pattern": "CYCLE"},
            {"selected": 0, "view": "detail"},
            {"ui": {"search": "no matches", "account": "missing", "tx": 99}},
            {"language": "zh"},
        ):
            with self.subTest(fields=fields):
                state = {**deepcopy(self.state), **fields}
                self.assertEqual(build_overview_context(self.data, state), baseline)

    def test_removing_overlapping_family_does_not_double_count_or_erase_shared_evidence(self):
        records = fixture_records()
        records["evidence"].append(
            {
                **records["evidence"][0],
                "family": "CYCLE",
                "rule_id": "cycle",
                "case_id": "cycle",
                "group_id": "cycle",
                "evidence_id": "cycle",
            }
        )
        full = build_overview_context(ReplayDataset(records), self.state)
        self.assertEqual(full["metrics"]["detected_transactions"], 2)
        self.assertEqual(full["metrics"]["observed_cases"], 2)
        for family in ("FAN-IN", "CYCLE"):
            with self.subTest(removed=family):
                ablated = deepcopy(records)
                ablated["evidence"] = [e for e in ablated["evidence"] if e["family"] != family]
                context = build_overview_context(ReplayDataset(ablated), self.state)
                self.assertEqual(context["metrics"]["detected_transactions"], 2)
                self.assertEqual(context["metrics"]["held_transactions"], 2)
                self.assertEqual(context["metrics"]["observed_cases"], 1)
                for pattern in context["patterns"]:
                    if pattern["id"] != family:
                        expected = next(p for p in full["patterns"] if p["id"] == pattern["id"])
                        self.assertEqual(pattern, expected)


class DetectionAblationTests(unittest.TestCase):
    def setUp(self):
        fixture = detection_fixture.DetectionTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.connection = fixture.connection
        edges = [
            (1, 1, 4),
            (2, 2, 4),
            (3, 3, 4),
            (4, 4, 5),
            (5, 4, 6),
            (6, 4, 7),
            (1, 10, 11),
            (1, 10, 12),
            (1, 10, 13),
            (2, 11, 14),
            (2, 12, 14),
            (2, 13, 14),
            (1, 20, 21),
            (2, 21, 22),
            (3, 22, 20),
            (1, 30, 31),
            (2, 31, 32),
            (3, 32, 33),
            (4, 33, 34),
            *((1, source, destination) for source in (40, 41, 42) for destination in (50, 51, 52)),
        ]
        fixture.add(
            [
                fixture.transaction(identifier, hour, source, destination)
                for identifier, (hour, source, destination) in enumerate(edges, 1)
            ]
        )
        self.cutoff = datetime(2022, 1, 1, 12)
        self.config = detection_fixture.CONFIG

    def test_each_detector_can_be_removed_without_changing_other_families(self):
        baseline, _ = generate(self.connection, self.cutoff, self.config)
        detectors = {
            "detect_fans": {"FAN-IN", "FAN-OUT"},
            "detect_gather_scatter": {"GATHER-SCATTER"},
            "detect_scatter_gather": {"SCATTER-GATHER"},
            "detect_layered_paths": {"STACK", "RANDOM"},
            "detect_bipartite": {"BIPARTITE"},
            "detect_cycles": {"CYCLE"},
        }
        self.assertEqual({case["family"] for case in baseline}, set.union(*detectors.values()))
        for name, families in detectors.items():
            with self.subTest(removed=name), patch(f"amlens.detection.engine.{name}"):
                ablated, _ = generate(self.connection, self.cutoff, self.config)
                self.assertEqual(
                    ablated, [case for case in baseline if case["family"] not in families]
                )

    def test_each_rule_can_be_removed_without_changing_other_selected_evidence(self):
        candidates, _ = generate(self.connection, self.cutoff, self.config)
        # Empty predicates isolate structural selection from frozen rule thresholds.
        rules = [
            {"rule_id": family, "family": family, "predicates": []}
            for family in sorted({case["family"] for case in candidates})
        ]
        ruleset = {"version": "ablation", "rules": rules}
        baseline = select_candidates(candidates, ruleset)
        self.assertEqual({case["family"] for case in baseline}, {rule["family"] for rule in rules})
        for removed in rules:
            with self.subTest(removed=removed["family"]):
                ablated = select_candidates(
                    candidates, {**ruleset, "rules": [rule for rule in rules if rule != removed]}
                )
                self.assertEqual(
                    ablated, [case for case in baseline if case["family"] != removed["family"]]
                )
        self.assertEqual(select_candidates(candidates, {**ruleset, "rules": []}), [])


if __name__ == "__main__":
    unittest.main()
