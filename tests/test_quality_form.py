"""Rule form parsing keeps validation strict without requiring a Tk window."""

import pytest

from dataflow.core.errors import DataFlowError
from dataflow.gui.quality_page import add_validation_rule, remove_validation_rule


def test_rule_form_merges_distinct_rules_without_mutating_saved_rules():
    original = {"required_columns": ["id"]}
    result = add_validation_rule(original, "Nonempty values", " id ")
    assert result["required_columns"] == ["id"]
    assert result["required_values"] == ["id"]
    assert original == {"required_columns": ["id"]}
    assert add_validation_rule(result, "Nonempty values", "id")["required_values"] == ["id"]
    assert add_validation_rule(result, "Required column", "missing")["required_columns"] == [
        "id",
        "missing",
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ('["A", 2, true]', ["A", 2, True]),
        ("A, 2, true", ["A", 2, True]),
        ('"New York, NY", Boston', ["New York, NY", "Boston"]),
    ],
)
def test_allowed_values_support_json_arrays_and_comma_literals(text, expected):
    result = add_validation_rule({}, "Allowed values", "category", text)
    assert result["allowed_values"] == {"category": expected}


@pytest.mark.parametrize(
    "kind,first,second",
    [
        ("Allowed values", "[invalid", ""),
        ("Allowed values", '[{"value":1}]', ""),
        ("Allowed values", "", ""),
        ("Numeric range", "true", ""),
        ("Numeric range", "NaN", ""),
        ("Numeric range", "20", "10"),
        ("Numeric range", "", ""),
        ("Date range", "26/10/2026", ""),
        ("Date range", "2027-01-01", "2026-01-01"),
    ],
)
def test_bad_form_rules_are_safe_domain_errors(kind, first, second):
    with pytest.raises(DataFlowError):
        add_validation_rule({}, kind, "column", first, second)


def test_range_rules_and_removal_preserve_other_rules():
    numeric = add_validation_rule({}, "Numeric range", "amount", "0", "10.5")
    result = add_validation_rule(numeric, "Date range", "date", "2026-01-01", "")
    assert result["numeric_ranges"] == {"amount": {"min": 0, "max": 10.5}}
    assert result["date_ranges"] == {"date": {"min": "2026-01-01"}}
    removed = remove_validation_rule(result, "numeric_ranges", "amount")
    assert removed["numeric_ranges"] == {}
    assert removed["date_ranges"] == {"date": {"min": "2026-01-01"}}
    assert result["numeric_ranges"] == {"amount": {"min": 0, "max": 10.5}}


def test_form_requires_column_and_recognized_rule_kind():
    for kind, column in (("Required column", "  "), ("typo", "id")):
        with pytest.raises(DataFlowError):
            add_validation_rule({}, kind, column)
