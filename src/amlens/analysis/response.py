"""Specify and validate model reports, including references to actual case evidence."""


class AnalysisError(Exception):
    """Expose only a safe, translatable error code to the browser."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _list(item: dict) -> dict:
    return {"type": "array", "items": item}


TEXT = {"type": "string"}
REFERENCES = {
    "transaction_ids": _list({"type": "integer"}),
    "feature_names": _list(TEXT),
}
FINDING = _object({"explanation": TEXT, **REFERENCES})
REPORT_SCHEMA = _object(
    {
        "summary": TEXT,
        "assessment": {
            "type": "string",
            "enum": ["supported_suspicion", "weak_support", "insufficient_evidence"],
        },
        "reason": TEXT,
        "pattern_assessment": _object(
            {
                "verdict": {
                    "type": "string",
                    "enum": ["matches", "partial", "unsupported", "insufficient_evidence"],
                },
                "explanation": TEXT,
                **REFERENCES,
            }
        ),
        "supporting_evidence": _list(FINDING),
        "counter_evidence": _list(FINDING),
        "normal_explanations": _list(TEXT),
        "missing_information": _list(TEXT),
        "next_steps": _list(TEXT),
    }
)

OVERVIEW_SCHEMA = _object(
    {
        "summary": TEXT,
        "findings": _list(
            _object({"title": TEXT, "explanation": TEXT, "metric_refs": _list(TEXT)})
        ),
        "focus_cases": _list(_object({"case_id": {"type": "integer"}, "reason": TEXT})),
        "next_steps": _list(TEXT),
        "limitations": _list(TEXT),
    }
)


def _validate(value, schema: dict) -> None:
    """Validate the small JSON-schema subset above without adding a runtime dependency."""
    kind = schema["type"]
    valid = False
    if kind == "object" and isinstance(value, dict):
        valid = set(value) == set(schema["properties"])
        if valid:
            for key, child in schema["properties"].items():
                _validate(value[key], child)
    elif kind == "array" and isinstance(value, list):
        valid = len(value) <= 100
        if valid:
            for item in value:
                _validate(item, schema["items"])
    elif kind == "string" and isinstance(value, str):
        valid = bool(value.strip()) and len(value) <= 10000
    elif kind == "integer":
        valid = type(value) is int
    if not valid or ("enum" in schema and value not in schema["enum"]):
        raise AnalysisError("invalid_output")


def validate_report(report: dict, context: dict) -> dict:
    _validate(report, REPORT_SCHEMA)
    transactions = {tx["id"] for tx in context["transactions"]}
    features = set(context["features"])
    findings = report["supporting_evidence"] + report["counter_evidence"]
    for finding in [*findings, report["pattern_assessment"]]:
        if not set(finding["transaction_ids"]) <= transactions:
            raise AnalysisError("invalid_output")
        if not set(finding["feature_names"]) <= features:
            raise AnalysisError("invalid_output")
    if any(not item["transaction_ids"] and not item["feature_names"] for item in findings):
        raise AnalysisError("invalid_output")
    return report


def validate_overview(report: dict, context: dict) -> dict:
    _validate(report, OVERVIEW_SCHEMA)
    if len(report["findings"]) > 6 or len(report["focus_cases"]) > 4:
        raise AnalysisError("invalid_output")
    for finding in report["findings"]:
        if not finding["metric_refs"] or not set(finding["metric_refs"]) <= set(context["metrics"]):
            raise AnalysisError("invalid_output")
    cases = {case["id"] for case in context["cases"] if case["status"] != "reviewed"}
    if any(case["case_id"] not in cases for case in report["focus_cases"]):
        raise AnalysisError("invalid_output")
    return report
