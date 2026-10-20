"""Compare a completed result database with the reference evidence in the project."""

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from amlens.config import RESULTS_DB
from amlens.db.detection_repository import detection_counts

SOURCE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = RESULTS_DB
DEFAULT_REFERENCE = SOURCE_ROOT / "tests" / "reference" / "expected-detection.json"
# Use canonical hashes to ignore JSON spacing and order differences.
# The reference directory contains source records and original file hashes.
EXPECTED_REFERENCE_DIGEST = "16a98e381548991aa47ae69a9c68361064a16488fb570f31aedd52e6e386b64a"
EXPECTED_RULESET_DIGEST = "79d346d5e3a6bb8f578e17fe7bf57d36535975bfaaca5b8a21b4f1e6c1b68682"
EXPECTED_COUNTS = {
    "FAN-IN": 27,
    "FAN-OUT": 47,
    "CYCLE": 76,
    "GATHER-SCATTER": 89,
    "SCATTER-GATHER": 60,
    "STACK": 25,
    "RANDOM": 21,
    "UNION": 330,
}


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _evidence_sets(cases: list, source: str) -> dict:
    """Validate records before indexing. Reject duplicate or invalid records."""
    if not isinstance(cases, list):
        raise ValueError(f"{source}: evidence must be a JSON list")
    evidence = {}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"{source}: evidence record {index} must be an object")
        family = case.get("family")
        if family not in EXPECTED_COUNTS or family == "UNION":
            raise ValueError(f"{source}: evidence record {index} has an unknown family")
        rule_id = family.lower().replace("-", "_") + "_v1"
        if case.get("rule_id") != rule_id:
            raise ValueError(f"{source}: evidence record {index} has an inconsistent rule")
        members = case.get("transaction_ids")
        if (
            not isinstance(members, list)
            or len(members) < 2
            or any(type(member) is not int or member <= 0 for member in members)
            or len(set(members)) != len(members)
        ):
            raise ValueError(f"{source}: evidence record {index} has invalid transaction IDs")
        members = tuple(sorted(members))
        identifier = hashlib.sha256(
            (family + ":" + ",".join(map(str, members))).encode()
        ).hexdigest()[:24]
        if case.get("case_id") != identifier:
            raise ValueError(f"{source}: evidence record {index} has an inconsistent case ID")
        key = (rule_id, identifier)
        if key in evidence:
            raise ValueError(f"{source}: duplicate evidence {rule_id}/{identifier}")
        evidence[key] = members
    return evidence


def _load_reference(path: Path) -> tuple[list, dict, str]:
    contents = path.read_bytes()
    cases = json.loads(contents)
    evidence = _evidence_sets(cases, "reference")
    canonical = [
        {
            "rule_id": case["rule_id"],
            "family": case["family"],
            "case_id": case["case_id"],
            "transaction_ids": sorted(case["transaction_ids"]),
        }
        for case in sorted(cases, key=lambda case: (case["rule_id"], case["case_id"]))
    ]
    if _digest(canonical) != EXPECTED_REFERENCE_DIGEST:
        raise ValueError("reference: evidence differs from the frozen POC export")
    return cases, evidence, hashlib.sha256(contents).hexdigest()


def _read_results(database: Path) -> dict:
    if not database.is_file():
        raise FileNotFoundError(f"Result database does not exist: {database}")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        if [row[0] for row in con.execute("PRAGMA integrity_check")] != ["ok"]:
            raise ValueError("database: SQLite integrity check failed")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("database: foreign-key check failed")
        records = [dict(row) for row in con.execute("SELECT * FROM evidence")]
        members = defaultdict(set)
        for row in con.execute("SELECT case_id, transaction_id FROM evidence_transactions"):
            members[row["case_id"]].add(row["transaction_id"])
        return {
            "records": records,
            "members": members,
            "actual": [json.loads(row["payload_json"]) for row in records],
            "counts": detection_counts(con),
            "metadata": {
                row[0]: json.loads(row[1]) for row in con.execute("SELECT * FROM metadata")
            },
            "batches": [
                row[0] for row in con.execute("SELECT cutoff FROM batches ORDER BY cutoff")
            ],
            "candidate_count": con.execute("SELECT SUM(candidate_count) FROM batches").fetchone()[
                0
            ],
        }


def verify_results(database: Path, reference: Path = DEFAULT_REFERENCE) -> dict:
    """Return a failed report for invalid inputs. Do not create or change either input."""
    database, reference = Path(database), Path(reference)
    report = {"passed": False, "checks": {}, "errors": [], "reference": str(reference)}
    try:
        expected, expected_sets, reference_sha = _load_reference(reference)
        report["checks"]["reference_valid"] = True
        report["reference_sha256"] = reference_sha
    except (OSError, ValueError, TypeError, KeyError) as error:
        report["checks"]["reference_valid"] = False
        report["errors"].append(str(error))
        return report
    try:
        data = _read_results(database)
        actual = data["actual"]
        actual_sets = _evidence_sets(actual, "database")
        counts, metadata = data["counts"], data["metadata"]
        ruleset = metadata.get("ruleset", {})
        summary = metadata.get("summary", {})
        if not isinstance(ruleset, dict) or not isinstance(summary, dict):
            raise ValueError("database: ruleset and summary metadata must be objects")
        fields = {
            "case_id": "case_id",
            "rule_id": "rule_id",
            "family": "family",
            "group_id": "evidence_group_id",
            "first_trigger": "first_trigger",
            "version": "evidence_version",
        }
        relational_consistency = all(
            all(record[column] == case.get(field) for column, field in fields.items())
            and data["members"][record["case_id"]] == set(case["transaction_ids"])
            for record, case in zip(data["records"], actual)
        )
        no_future_evidence = all(
            datetime.fromisoformat(case["evidence_start"])
            <= datetime.fromisoformat(case["evidence_end"])
            < datetime.fromisoformat(case["first_trigger"])
            and case["first_trigger"] in data["batches"]
            for case in actual
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
        report["checks"]["database_valid"] = False
        report["errors"].append(str(error))
        return report
    families = {case["family"] for case in expected}

    def members(cases, family):
        return {tx for case in cases if case["family"] == family for tx in case["transaction_ids"]}

    cutoffs = [str(datetime(2022, 9, 1, 6) + timedelta(hours=6 * i)) for i in range(71)]
    report["checks"].update(
        {
            "database_valid": True,
            "complete": metadata.get("status") == "complete",
            "summary_present": isinstance(summary.get("wall_seconds"), (int, float))
            and summary["wall_seconds"] >= 0,
            "ruleset_equal": _digest(ruleset) == EXPECTED_RULESET_DIGEST,
            "source_rows": metadata.get("source_transactions") == 5078345,
            "71_batches": data["batches"] == cutoffs,
            "counts_equal": {row["pattern"]: row["transaction_count"] for row in counts}
            == EXPECTED_COUNTS,
            "evidence_members_equal": actual_sets == expected_sets,
            "relational_evidence_equal": relational_consistency,
            "1221_evidence_sets": len(actual_sets) == 1221,
            "candidate_snapshots_equal": data["candidate_count"] == 3787421,
            "49_structure_groups": counts[-1]["structure_count"] == 49,
            "per_pattern_transaction_ids_equal": all(
                members(actual, family) == members(expected, family) for family in families
            ),
            "no_future_evidence": no_future_evidence,
        }
    )
    report.update(
        {
            "passed": all(report["checks"].values()),
            "counts": counts,
            "ruleset_version": ruleset.get("version"),
            "detection_wall_seconds": summary.get("wall_seconds"),
            "candidate_snapshots": data["candidate_count"],
            "missing_evidence": len(expected_sets.keys() - actual_sets.keys()),
            "unexpected_evidence": len(actual_sets.keys() - expected_sets.keys()),
        }
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
        help="Use a JSON reference export. The default is tests/reference/expected-detection.json.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_results(args.database, args.reference)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        if args.output.resolve() in {args.database.resolve(), args.reference.resolve()}:
            parser.error("--output must differ from --database and --reference")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
