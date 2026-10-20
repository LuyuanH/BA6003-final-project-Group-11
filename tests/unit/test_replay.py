"""Do tests for evidence time limits, structure groups, and review state in each session."""

import unittest
from copy import deepcopy

from amlens.presenters import minute_index
from amlens.services.case_service import ReplayDataset
from amlens.services.dashboard_service import dashboard_snapshot
from amlens.services.replay_service import apply_action, initial_state


def fixture_records():
    transactions = []
    accounts = {}
    for tx_id in range(1, 9):
        sender, receiver = str(tx_id), str(tx_id + 1)
        transactions.append(
            {
                "transaction_id": tx_id,
                "event_time": f"2022-09-01 0{tx_id}:00:00",
                "sender_bank": "1",
                "sender_account": sender,
                "receiver_bank": "1",
                "receiver_account": receiver,
                "received": 100,
                "received_currency": "US Dollar",
                "paid": 100,
                "paid_currency": "US Dollar",
                "payment_method": "ACH",
                "received_raw": "1.00",
                "paid_raw": "1.00",
            }
        )
        for account in (sender, receiver):
            accounts[("1", account)] = {
                "bank_id": "1",
                "account_number": account,
                "bank_name": "Test Bank",
                "entity_id": account,
                "entity_name": "Entity " + account,
            }
    return {
        "metadata": {},
        "batches": [{"cutoff": "2022-09-01 18:00:00"}],
        "timeline": [(row["event_time"], 1) for row in transactions],
        "transactions": transactions,
        "accounts": accounts,
        "evidence": [
            {
                "case_id": "first",
                "group_id": "hub",
                "rule_id": "fan",
                "family": "FAN-IN",
                "first_trigger": "2022-09-01 06:00:00",
                "version": 1,
                "evidence_start": "2022-09-01 01:00:00",
                "evidence_end": "2022-09-01 02:00:00",
                "transaction_ids": [1, 2],
            },
            {
                "case_id": "second",
                "group_id": "hub",
                "rule_id": "fan",
                "family": "FAN-IN",
                "first_trigger": "2022-09-01 12:00:00",
                "version": 2,
                "evidence_start": "2022-09-01 02:00:00",
                "evidence_end": "2022-09-01 03:00:00",
                "transaction_ids": [2, 3],
            },
        ],
    }


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.data = ReplayDataset(fixture_records())
        self.state = initial_state(self.data, 0)

    def action(self, action, value=None, now=0, **extra):
        apply_action(
            self.state,
            self.data,
            {
                "id": str(self.state["revision"]) + action,
                "action": action,
                "value": value,
                **extra,
            },
            now,
        )

    def test_cases_appear_at_detection_time_not_last_transaction(self):
        self.state["cursor"] = minute_index("2022-09-01 05:59:00")
        self.assertEqual(self.data.visible(self.state), [])
        self.state["cursor"] += 1
        case = self.data.visible(self.state)[0]
        self.assertEqual(case.evidence_id, "first")
        self.assertEqual(
            dashboard_snapshot(self.data, self.state)["detail"]["transactions"][0]["id"], 1
        )

    def test_latest_evidence_is_complete_and_history_is_counted_once(self):
        self.state["cursor"] = self.data.end
        snapshot = dashboard_snapshot(self.data, self.state)
        self.assertEqual(len(snapshot["queue"]), 1)
        self.assertEqual(snapshot["detail"]["version"], 2)
        self.assertEqual([row["id"] for row in snapshot["detail"]["transactions"]], [2, 3])
        self.assertEqual(snapshot["hold"], 3)
        self.assertEqual(snapshot["patterns"][0]["count"], 3)
        self.assertEqual(snapshot["processed"], 8)
        self.assertEqual(self.data.end, minute_index("2022-09-01 18:00:00"))

    def test_new_evidence_resets_review_and_rejects_stale_review(self):
        self.state["cursor"] = minute_index("2022-09-01 06:00:00")
        self.action("open", 0)
        self.action("status", "reviewed", evidenceId="first")
        self.assertEqual(dashboard_snapshot(self.data, self.state)["hold"], 0)
        self.state["cursor"] = minute_index("2022-09-01 12:00:00")
        self.assertEqual(dashboard_snapshot(self.data, self.state)["pending"], 1)
        self.action("status", "reviewed", evidenceId="first")
        self.assertEqual(dashboard_snapshot(self.data, self.state)["pending"], 1)
        self.action("status", "reviewed", evidenceId="second")
        self.assertEqual(dashboard_snapshot(self.data, self.state)["reviewed"], 1)

    def test_all_groups_are_visible_without_per_pattern_cap(self):
        records = fixture_records()
        first = records["evidence"][0]
        records["evidence"] = [
            {**first, "case_id": str(index), "group_id": str(index)} for index in range(20)
        ]
        data = ReplayDataset(records)
        self.state["cursor"] = data.end
        snapshot = dashboard_snapshot(data, self.state)
        self.assertEqual(len(snapshot["queue"]), 20)
        self.assertEqual(snapshot["hold"], 2)
        self.assertEqual(snapshot["patterns"][0]["cases"], 20)

    def test_forward_only_navigation_keeps_replay_running(self):
        self.action("play")
        self.action("tick", now=10)
        cursor = self.state["cursor"]
        self.action("play", now=10)
        self.assertTrue(self.state["playing"])
        for action in ("seek", "reset", "date", "next"):
            self.action(action, 0, now=10)
            self.assertEqual(self.state["cursor"], cursor)
            self.assertTrue(self.state["playing"])
        self.action("open", 0, now=10)
        self.assertTrue(self.state["playing"])
        self.action("speed", 14400, now=10)
        self.action("speed", 28800, now=10)
        self.action("tick", now=1000)
        self.assertEqual(self.state["cursor"], self.data.end)
        self.assertFalse(self.state["playing"])
        self.action("play", now=1001)
        self.assertFalse(self.state["playing"])

    def test_duplicate_packet_is_idempotent(self):
        self.action("play")
        packet = {"id": "same", "action": "tick"}
        apply_action(self.state, self.data, packet, 10)
        before = deepcopy(self.state)
        apply_action(self.state, self.data, packet, 20)
        self.assertEqual(self.state, before)

    def test_no_future_open_or_detail_and_no_implicit_pause(self):
        self.action("open", 0)
        self.assertIsNone(self.state["selected"])
        self.action("play")
        self.action("tick", now=10)
        self.action("open", 0, now=10)
        self.assertEqual(self.state["view"], "detail")
        self.assertTrue(self.state["playing"])
        snapshot = dashboard_snapshot(self.data, self.state)
        self.assertEqual(snapshot["detail"]["evidenceId"], "first")
        self.assertTrue(
            all(tx["time"] < self.state["cursor"] for tx in snapshot["detail"]["transactions"])
        )

    def test_money_is_grouped_by_currency_without_rounding_source_values(self):
        records = fixture_records()
        records["transactions"][0].update(paid_raw="0.12345678", paid_currency="Bitcoin")
        data = ReplayDataset(records)
        self.state["cursor"] = minute_index("2022-09-01 06:00:00")
        detail = dashboard_snapshot(data, self.state)["detail"]
        self.assertEqual(detail["transactions"][0]["paid"], "0.12345678")
        self.assertEqual(detail["transactions"][0]["lines"], [2])
        self.assertEqual(
            detail["amounts"],
            [
                {"currency": "Bitcoin", "amount": "0.12345678"},
                {"currency": "US Dollar", "amount": "1.00"},
            ],
        )

    def test_future_evidence_fails_closed(self):
        records = fixture_records()
        records["evidence"][0]["first_trigger"] = "2022-09-01 02:00:00"
        with self.assertRaisesRegex(ValueError, "截止时间"):
            ReplayDataset(records)

    def test_bipartite_is_explicitly_not_enabled(self):
        snapshot = dashboard_snapshot(self.data, self.state)
        self.assertFalse(
            next(row for row in snapshot["patterns"] if row["id"] == "BIPARTITE")["enabled"]
        )


if __name__ == "__main__":
    unittest.main()
