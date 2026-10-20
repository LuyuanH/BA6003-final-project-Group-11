"""Do regression tests for time limits, structures, and SQL selection without labels."""

import sqlite3
import unittest
from datetime import datetime, timedelta

from amlens.db.candidate_queries import stage_candidates, window_edges
from amlens.db.pattern_queries import (
    count_by_pattern,
    count_union,
    record_selected_candidates,
    select_candidates,
)
from amlens.db.schema import EDGE_VIEW, INDEX_SCHEMA, create_observation_schema
from amlens.detection.engine import query
from amlens.detection.rules import load_ruleset

CONFIG = {
    **load_ruleset()["search_config"],
    "windows_hours": [24],
}


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        create_observation_schema(self.connection)
        self.connection.executescript(INDEX_SCHEMA)
        self.connection.executescript(EDGE_VIEW)

    def tearDown(self):
        self.connection.close()

    def transaction(
        self, identifier, hour, source, destination, currency="USD", amount=10000, method="ACH"
    ):
        return (
            identifier,
            (datetime(2022, 1, 1) + timedelta(hours=hour)).isoformat(sep=" "),
            source,
            destination,
            amount,
            currency,
            amount,
            currency,
            method,
        )

    def add(self, rows):
        for (
            identifier,
            time,
            source,
            destination,
            received,
            received_currency,
            paid,
            paid_currency,
            method,
        ) in rows:
            self.connection.executemany(
                "INSERT OR IGNORE INTO nodes (node_id, bank, account) VALUES (?, '0', ?)",
                [(source, str(source)), (destination, str(destination))],
            )
            self.connection.execute(
                "INSERT INTO transactions VALUES (?, ?, '0', ?, '0', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    time,
                    str(source),
                    str(destination),
                    received,
                    received_currency,
                    paid,
                    paid_currency,
                    method,
                    str(received),
                    str(paid),
                ),
            )

    def find(self, family, cutoff="2022-01-01 12:00:00", windows=None):
        ruleset = {
            "version": "fixture",
            "search_config": {**CONFIG, "windows_hours": windows or [24]},
            "rules": [{"rule_id": "fixture", "family": family, "predicates": []}],
        }
        return query(cutoff, ruleset, con=self.connection)[0]

    def test_cycle_waits_for_final_edge_and_excludes_cutoff_equality(self):
        self.add(
            [
                self.transaction(1, 1, 1, 2),
                self.transaction(2, 2, 2, 3),
                self.transaction(3, 6, 3, 1),
            ]
        )
        self.assertEqual(self.find("CYCLE", "2022-01-01 06:00:00"), [])
        found = self.find("CYCLE", "2022-01-01 06:01:00")
        self.assertEqual([case["transaction_ids"] for case in found], [[1, 2, 3]])

    def test_nonchronological_cycle_is_excluded(self):
        self.add(
            [
                self.transaction(1, 1, 1, 2),
                self.transaction(2, 3, 2, 3),
                self.transaction(3, 2, 3, 1),
            ]
        )
        self.assertEqual(self.find("CYCLE"), [])

    def test_fans_count_all_payment_methods_in_background(self):
        for family, reverse in [("FAN-OUT", False), ("FAN-IN", True)]:
            with self.subTest(family=family):
                self.connection.execute("DELETE FROM transactions")
                self.add(
                    [
                        self.transaction(
                            i,
                            i,
                            i + 1 if reverse else 1,
                            1 if reverse else i + 1,
                            method="Wire" if i == 4 else "ACH",
                        )
                        for i in range(1, 5)
                    ]
                )
                case = self.find(family)[0]
                self.assertEqual(case["features"]["hub_ach_fraction"], 0.75)
                self.assertEqual(case["transaction_ids"], [1, 2, 3])

    def test_gather_scatter_uses_local_phase_transition(self):
        self.add(
            [
                self.transaction(1, 1, 1, 3),
                self.transaction(2, 2, 2, 3),
                self.transaction(3, 3, 3, 4),
                self.transaction(4, 4, 3, 5),
            ]
        )
        self.assertEqual(self.find("GATHER-SCATTER")[0]["transaction_ids"], [1, 2, 3, 4])

    def test_scatter_gather_requires_distinct_intermediaries(self):
        self.add(
            [
                self.transaction(1, 1, 1, 2),
                self.transaction(2, 2, 1, 3),
                self.transaction(3, 3, 2, 4),
                self.transaction(4, 4, 3, 4),
            ]
        )
        self.assertEqual(self.find("SCATTER-GATHER")[0]["transaction_ids"], [1, 2, 3, 4])

    def test_stack_fx_transition_does_not_claim_amount_match(self):
        self.add(
            [
                self.transaction(1, 1, 1, 2),
                self.transaction(2, 2, 2, 3, currency="JPY", amount=1000000),
            ]
        )
        case = self.find("STACK")[0]
        self.assertEqual(case["features"]["currency_switches"], 1)
        self.assertEqual(case["features"]["compatible_pairs"], 0)

    def test_random_emits_three_and_four_hop_complete_paths(self):
        self.add([self.transaction(i, i, i, i + 1) for i in range(1, 5)])
        sets = {tuple(case["transaction_ids"]) for case in self.find("RANDOM")}
        self.assertEqual(sets, {(1, 2, 3), (2, 3, 4), (1, 2, 3, 4)})

    def test_window_start_is_inclusive_and_cutoff_is_exclusive(self):
        self.add([self.transaction(1, 0, 1, 2), self.transaction(2, 24, 2, 3)])
        edges = window_edges(self.connection, datetime(2022, 1, 2), 24)
        self.assertEqual([edge["transaction_id"] for edge in edges], [1])

    def test_future_data_cannot_change_earlier_result(self):
        self.add([self.transaction(i, i, 1, i + 1) for i in range(1, 4)])
        early = self.find("FAN-OUT", "2022-01-01 06:00:00")
        self.add([self.transaction(4, 7, 1, 5)])
        self.assertEqual(self.find("FAN-OUT", "2022-01-01 06:00:00"), early)
        later = self.find("FAN-OUT")[0]
        self.assertEqual(early[0]["evidence_group_id"], later["evidence_group_id"])
        self.assertNotEqual(early[0]["case_id"], later["case_id"])

    def test_multiple_windows_deduplicate_complete_evidence(self):
        self.add([self.transaction(i, i, 1, i + 1) for i in range(1, 4)])
        found = self.find("FAN-OUT", windows=[12, 24])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["features"]["window_hours"], 12)


class FrozenSelectionTests(unittest.TestCase):
    def candidate(self, identifier, family, members, features):
        return {
            "case_id": identifier,
            "family": family,
            "transaction_ids": members,
            "decision_time": "2022-01-01 06:00:00",
            "features": features,
        }

    def test_all_frozen_sql_predicates_and_window_isolation(self):
        ruleset = load_ruleset()
        candidates = []
        for rule in ruleset["rules"]:
            thresholds = {p["feature"]: p["value"] for p in rule["predicates"]}
            candidates.append(self.candidate(rule["rule_id"], rule["family"], [1, 2], thresholds))
            failing = dict(thresholds)
            first = rule["predicates"][0]
            failing[first["feature"]] += -1 if first["operator"] == ">=" else 1
            # Reuse the evidence ID in a different window. Exclude members that fail the rule.
            candidates.append(self.candidate(rule["rule_id"], rule["family"], [999], failing))
        selected = select_candidates(candidates, ruleset)
        self.assertEqual(len(selected), 7)
        self.assertTrue(all(case["transaction_ids"] == [1, 2] for case in selected))
        con = stage_candidates(candidates)
        try:
            record_selected_candidates(con)
            self.assertEqual(
                count_union(con),
                {
                    "pattern": "UNION",
                    "transaction_count": 2,
                    "evidence_set_count": 7,
                },
            )
            self.assertTrue(all(row["transaction_count"] == 2 for row in count_by_pattern(con)))
        finally:
            con.close()

    def test_missing_feature_does_not_pass_sql_rule(self):
        candidate = self.candidate("missing", "FAN-IN", [1, 2], {"edges": 12})
        self.assertEqual(select_candidates([candidate], load_ruleset()), [])


if __name__ == "__main__":
    unittest.main()
