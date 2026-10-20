"""Apply SQL rules to candidate features and transaction members."""

import sqlite3

from amlens.db.candidate_queries import FEATURE_COLUMNS, read_sql, stage_candidates


def find_fan_in_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("fan_in.sql")).fetchall()


def find_fan_out_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("fan_out.sql")).fetchall()


def find_cycle_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("cycle.sql")).fetchall()


def find_gather_scatter_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("gather_scatter.sql")).fetchall()


def find_scatter_gather_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("scatter_gather.sql")).fetchall()


def find_stack_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("stack.sql")).fetchall()


def find_random_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(read_sql("random.sql")).fetchall()


FROZEN_QUERIES = {
    "FAN-IN": find_fan_in_candidates,
    "FAN-OUT": find_fan_out_candidates,
    "CYCLE": find_cycle_candidates,
    "GATHER-SCATTER": find_gather_scatter_candidates,
    "SCATTER-GATHER": find_scatter_gather_candidates,
    "STACK": find_stack_candidates,
    "RANDOM": find_random_candidates,
}


def _find_custom_candidates(con: sqlite3.Connection, rule: dict) -> list[sqlite3.Row]:
    """Validate test rule identifiers. Bind each predicate value to a SQL parameter."""
    conditions = ["family = ?"]
    parameters = [rule["family"]]
    for predicate in rule["predicates"]:
        feature, operator = predicate["feature"], predicate["operator"]
        if feature not in FEATURE_COLUMNS or operator not in {">=", "<="}:
            raise ValueError(f"Unsupported feature or operator: {feature!r}, {operator!r}")
        conditions.append(f'"{feature}" {operator} ?')
        parameters.append(predicate["value"])
    sql = "SELECT * FROM candidate_features WHERE " + " AND ".join(conditions)
    return con.execute(sql + " ORDER BY candidate_ordinal", parameters).fetchall()


def select_candidates(candidates: list[dict], ruleset: dict) -> list[dict]:
    """Run the SQL rules. Select the first matching window for each rule and evidence ID."""
    from amlens.detection.rules import load_ruleset

    frozen_rules = {rule["family"]: rule for rule in load_ruleset()["rules"]}
    selected = {}
    con = stage_candidates(candidates)
    try:
        for rule in ruleset["rules"]:
            family = rule["family"]
            frozen = frozen_rules.get(family)
            if frozen and rule["predicates"] == frozen["predicates"]:
                rows = FROZEN_QUERIES[family](con)
            else:
                rows = _find_custom_candidates(con, rule)
            for row in rows:
                case = candidates[row["candidate_ordinal"]]
                key = (rule["rule_id"], case["case_id"])
                if key not in selected:
                    selected[key] = {
                        **case,
                        "rule_id": rule["rule_id"],
                        "ruleset_version": ruleset["version"],
                        "explanation": rule["predicates"],
                    }
        return sorted(selected.values(), key=lambda case: (case["rule_id"], case["case_id"]))
    finally:
        con.close()


def record_selected_candidates(con: sqlite3.Connection) -> None:
    """Record the seven rule selections for SQL counts and result comparisons."""
    for family, query in FROZEN_QUERIES.items():
        rule_id = family.lower().replace("-", "_") + "_v1"
        con.executemany(
            "INSERT OR IGNORE INTO selected_candidates VALUES (?, ?)",
            ((row["candidate_ordinal"], rule_id) for row in query(con)),
        )


def count_by_pattern(con: sqlite3.Connection) -> list[dict]:
    """Count unique transaction members and evidence sets for each rule."""
    return [dict(row) for row in con.execute(read_sql("count_by_pattern.sql"))]


def count_union(con: sqlite3.Connection) -> dict:
    """Count each selected transaction once across all rules."""
    return dict(con.execute(read_sql("count_union.sql")).fetchone())
