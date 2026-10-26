"""Read-only quality checks produce exact rejected source records and safe diagnostics."""

import json

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from dataflow.core.errors import DataFlowError


def validate(frame, **rules):
    from dataflow.core.quality import ValidationRules, validate_data

    return validate_data(frame, ValidationRules(**rules))


def test_all_rules_identify_exact_rejected_records_without_mutating_source(tmp_path):
    from dataflow.core.io import read_table, write_table

    frame = pd.DataFrame(
        {
            "id": ["001", "002", "002", "004"],
            "name": ["A", "  ", "private-cell", "D"],
            "status": ["ok", "bad", "ok", "ok"],
            "amount": [5, 11, 3, None],
            "day": ["2026-01-01", "2026-01-02", "2025-12-31", None],
        },
        index=[8, 8, 3, 90],
    )
    original = frame.copy(deep=True)
    report = validate(
        frame,
        required_columns=["id"],
        required_values=["name"],
        unique_columns=["id"],
        allowed_values={"status": ["ok"]},
        numeric_ranges={"amount": {"min": 0, "max": 10}},
        date_ranges={"day": {"min": "2026-01-01", "max": "2026-12-31"}},
    )
    assert report.summary() == {
        "rows": 4,
        "valid_rows": 2,
        "invalid_rows": 2,
        "issue_count": 6,
        "schema_errors": [],
    }
    assert_frame_equal(frame, original)
    assert report.problem_rows["id"].tolist() == ["002", "002"]
    assert report.problem_rows[report.source_record_column].tolist() == [3, 4]
    assert report.issues["record"].tolist() == [3, 3, 4, 3, 3, 4]
    assert "private-cell" not in report.issues.to_json()
    assert "private-cell" not in report.problem_rows[report.reasons_column].str.cat()
    output = write_table(report.problem_rows, tmp_path / "rejected.xlsx")
    exported = read_table(output, import_options={"column_types": {"id": "string"}})
    assert exported["id"].tolist() == ["002", "002"]
    assert exported["name"].tolist() == ["  ", "private-cell"]


@pytest.mark.parametrize("rows", [0, 2])
def test_missing_columns_are_schema_errors_and_invalidate_all_existing_records(rows):
    report = validate(pd.DataFrame({"id": list(range(rows))}), required_columns=["absent"])
    summary = report.summary()
    assert summary["schema_errors"]
    assert summary["invalid_rows"] == rows
    assert summary["valid_rows"] == 0
    assert len(report.problem_rows) == rows


@pytest.mark.parametrize(
    "rule", ["required_values", "unique_columns", "allowed_values", "numeric_ranges", "date_ranges"]
)
def test_missing_rule_columns_are_reported_even_for_empty_input(rule):
    value = (
        ["missing"]
        if rule in {"required_values", "unique_columns"}
        else {
            "missing": []
            if rule == "allowed_values"
            else {"min": "2026-01-01" if rule == "date_ranges" else 0}
        }
    )
    report = validate(pd.DataFrame({"id": []}), **{rule: value})
    assert report.summary()["schema_errors"]


def test_rejected_row_metadata_never_overwrites_user_columns():
    frame = pd.DataFrame(
        {
            "_source_record": ["keep"],
            "_source_record_2": ["also"],
            "_validation_reasons": ["private-cell"],
            "id": [None],
        }
    )
    report = validate(frame, required_values=["id"])
    assert report.problem_rows["_source_record"].tolist() == ["keep"]
    assert report.problem_rows["_validation_reasons"].tolist() == ["private-cell"]
    assert report.source_record_column == "_source_record_3"
    assert report.reasons_column == "_validation_reasons_2"
    assert report.problem_rows[report.source_record_column].tolist() == [2]


def test_empty_and_whitespace_missing_values_are_excluded_from_other_rules():
    frame = pd.DataFrame({"value": [None, "", "  ", 0, 0, "private-cell"]})
    report = validate(frame, unique_columns=["value"], numeric_ranges={"value": {"min": 0}})
    assert report.problem_rows[report.source_record_column].tolist() == [5, 6, 7]
    assert set(report.issues["rule"]) == {"unique", "numeric_range"}


def test_allowed_values_and_bounds_do_not_accept_bad_nonempty_values():
    frame = pd.DataFrame(
        {"a": [0, 1, None], "n": ["bad", "0", None], "d": ["bad", "2026-10-26", ""]}
    )
    report = validate(
        frame,
        allowed_values={"a": [0]},
        numeric_ranges={"n": {"min": 0}},
        date_ranges={"d": {"min": "2026-10-26", "max": "2026-10-26"}},
    )
    assert report.summary()["invalid_rows"] == 2
    assert report.summary()["issue_count"] == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": []},
        {"required_columns": "id"},
        {"required_values": [""]},
        {"unique_columns": ["id", "id"]},
        {"allowed_values": {"id": "A"}},
        {"allowed_values": {"id": [[1]]}},
        {"numeric_ranges": {"id": {"min": True}}},
        {"numeric_ranges": {"id": {"min": 3, "max": 2}}},
        {"numeric_ranges": {"id": {"min": float("nan")}}},
        {"numeric_ranges": {"id": {"typo": 1}}},
        {"date_ranges": {"id": {"min": "26/10/2026"}}},
        {"date_ranges": {"id": {"min": "2027-01-01", "max": "2026-01-01"}}},
    ],
)
def test_invalid_rules_are_domain_errors(payload):
    from dataflow.core.quality import ValidationRules

    with pytest.raises(DataFlowError):
        ValidationRules.from_dict(payload)


def test_rules_json_roundtrip_and_duplicate_key_rejection(tmp_path):
    from dataflow.core.quality import ValidationRules

    payload = {"required_values": ["id"], "allowed_values": {"id": ["A", None, 0]}}
    rules = ValidationRules.from_dict(payload)
    payload["required_values"].clear()
    assert rules.required_values == ["id"]
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules.to_dict()), encoding="utf-8")
    assert ValidationRules.from_json(path).to_dict() == rules.to_dict()
    path.write_text('{"required_values":[],"required_values":["id"]}', encoding="utf-8")
    with pytest.raises(DataFlowError):
        ValidationRules.from_json(path)


def test_numeric_bounds_compare_large_integer_identifiers_without_float_rounding():
    report = validate(
        pd.DataFrame({"id": [9007199254740993, 9007199254740992]}),
        numeric_ranges={"id": {"min": 9007199254740993}},
    )
    assert report.problem_rows["id"].tolist() == [9007199254740992]


def test_validation_cooperates_with_cancellation_and_keeps_source_unchanged():
    from dataflow.core.jobs import JobCancelled, JobControl
    from dataflow.core.quality import ValidationRules, validate_data

    frame = pd.DataFrame({"id": [1, 2]})
    original = frame.copy(deep=True)
    control = JobControl(lambda event: control.cancel())
    with pytest.raises(JobCancelled):
        validate_data(frame, ValidationRules(required_values=["id"]), control=control)
    assert_frame_equal(frame, original)
