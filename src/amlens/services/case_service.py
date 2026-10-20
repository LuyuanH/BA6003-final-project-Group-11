"""Group evidence and supply case details for the current replay time."""

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from amlens.presenters import account_key, account_record, minute_index, transaction_record

PATTERN_ORDER = (
    "FAN-IN",
    "FAN-OUT",
    "CYCLE",
    "GATHER-SCATTER",
    "SCATTER-GATHER",
    "BIPARTITE",
    "STACK",
    "RANDOM",
)
PATTERN_NAMES = (
    "集中收款",
    "分散付款",
    "循环转账",
    "归集后分散",
    "分散后归集",
    "双层互转",
    "层层转移",
    "混合路径",
)


@dataclass(frozen=True)
class EvidenceCase:
    """Store one complete evidence version within a stable structure group."""

    id: int
    evidence_id: str
    group_id: str
    rule_id: str
    pattern: str
    version: int
    discovered: int
    start: int
    end: int
    transactions: tuple[int, ...]


class ReplayDataset:
    """Keep source records unchanged. Use time indexes to limit evidence to the current replay time."""

    def __init__(self, records: dict[str, Any]):
        self.metadata = records["metadata"]
        self.times = [minute_index(timestamp) for timestamp, _ in records["timeline"]]
        if not self.times or not records["batches"]:
            raise ValueError("原始交易或检测批次为空，请重新准备数据。")
        self.prefix = [0]
        for _, count in records["timeline"]:
            self.prefix.append(self.prefix[-1] + count)
        self.start = self.times[0] // 1440 * 1440
        self.end = max(self.times[-1], minute_index(records["batches"][-1]["cutoff"]))
        self.transactions = {
            row["transaction_id"]: transaction_record(row) for row in records["transactions"]
        }
        self.accounts = {
            account_key(*key): account_record(row) for key, row in records["accounts"].items()
        }
        group_ids = {}
        evidence = []
        ordered = sorted(
            records["evidence"],
            key=lambda row: (row["first_trigger"], row["version"], row["case_id"]),
        )
        for row in ordered:
            group_key = (row["rule_id"], row["group_id"])
            group_ids.setdefault(group_key, len(group_ids))
            case = EvidenceCase(
                id=group_ids[group_key],
                evidence_id=row["case_id"],
                group_id=row["group_id"],
                rule_id=row["rule_id"],
                pattern=row["family"],
                version=row["version"],
                discovered=minute_index(row["first_trigger"]),
                start=minute_index(row["evidence_start"]),
                end=minute_index(row["evidence_end"]),
                transactions=tuple(row["transaction_ids"]),
            )
            if any(self.transactions[tx]["time"] >= case.discovered for tx in case.transactions):
                raise ValueError("检测证据包含截止时间之后的交易，拒绝回放。")
            evidence.append(case)
        self.evidence = tuple(evidence)
        identity = {
            "observations": self.metadata.get("observation_signature"),
            "ruleset": self.metadata.get("ruleset"),
            "timeline": records["timeline"],
            "cutoffs": [batch["cutoff"] for batch in records["batches"]],
            "evidence": [
                (case.evidence_id, case.group_id, case.rule_id, case.version, case.discovered)
                for case in self.evidence
            ],
        }
        self.fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def processed(self, start: int, cursor: float) -> int:
        return (
            self.prefix[bisect_right(self.times, cursor)]
            - self.prefix[bisect_left(self.times, start)]
        )

    def discovered_evidence(self, cursor: float) -> list[EvidenceCase]:
        return [case for case in self.evidence if case.discovered <= cursor]

    def visible(self, state: dict[str, Any]) -> list[EvidenceCase]:
        """Show the latest complete evidence version for each structure."""
        latest = {}
        for case in self.discovered_evidence(state["cursor"]):
            if case.id not in latest or case.version > latest[case.id].version:
                latest[case.id] = case
        return sorted(latest.values(), key=lambda case: (case.discovered, case.id))

    def status(self, case: EvidenceCase, state: dict[str, Any]) -> str:
        review = state["statuses"].get(str(case.id), {})
        # Apply each review decision to the evidence version that the reviewer saw.
        return (
            review.get("status", "pending")
            if review.get("evidence_id") == case.evidence_id
            else "pending"
        )

    def detail(self, case: EvidenceCase, status: str) -> dict[str, Any]:
        transactions = sorted(
            (self.transactions[tx] for tx in case.transactions),
            key=lambda tx: (tx["time"], tx["id"]),
        )
        keys = sorted(
            {
                account_key(tx[bank], tx[account])
                for tx in transactions
                for bank, account in (("fromBank", "from"), ("toBank", "to"))
            }
        )
        amounts = defaultdict(Decimal)
        for transaction in transactions:
            amounts[transaction["paymentCurrency"]] += Decimal(transaction["paid"])
        return {
            "id": case.id,
            "evidenceId": case.evidence_id,
            "groupId": case.group_id,
            "version": case.version,
            "pattern": case.pattern,
            "status": status,
            "start": case.start,
            "end": case.discovered,
            "evidenceEnd": case.end,
            "nodes": [self.accounts[key] for key in keys],
            "transactions": transactions,
            "amounts": [
                {"currency": currency, "amount": format(amount, "f")}
                for currency, amount in sorted(amounts.items())
            ],
        }
