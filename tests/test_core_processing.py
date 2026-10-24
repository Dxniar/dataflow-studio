"""Hand-checked fixtures exercise cleaning, transforms, and actual metrics."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from dataflow.core.configuration import PipelineConfig
from dataflow.core.errors import DataFlowError
from dataflow.core.processor import process_frame


def run(frame, **options):
    return process_frame(frame, PipelineConfig.from_dict(options))


def test_default_is_non_destructive_and_result_owns_copies():
    frame = pd.DataFrame({"id": [1, 1], "name": [" A ", None]})
    result = run(frame)
    assert_frame_equal(result.processed, frame)
    assert result.operations == []
    result.processed.loc[0, "name"] = "changed"
    result.original.loc[1, "name"] = "different"
    assert frame.loc[0, "name"] == " A "
    assert pd.isna(frame.loc[1, "name"])


def test_ordered_cleaning_and_factual_metrics():
    frame = pd.DataFrame(
        {" Customer ID ": [" 2 ", "1", "1", None], " City ": [" almaty ", "Astana", "Astana", "  "]}
    )
    result = run(
        frame,
        trim_whitespace=True,
        drop_empty_rows=True,
        normalize_columns=True,
        standardize_values={"city": {"almaty": "Алматы"}},
        convert_types={"customer_id": "integer"},
        drop_duplicates=True,
        deduplicate_by=["customer_id"],
        sort_by=["customer_id"],
    )
    assert result.processed["customer_id"].tolist() == [1, 2]
    assert result.processed["city"].tolist() == ["Astana", "Алматы"]
    summary = result.summary()
    assert summary["original_rows"] == 4
    assert summary["processed_rows"] == 2
    assert summary["duplicates_removed"] == 1
    assert summary["missing_before"] == 2
    assert summary["missing_after"] == 0
    assert summary["files_processed"] == 1
    assert summary["elapsed_seconds"] >= 0
    assert len(summary["operations"]) == 7


def test_blank_missing_fill_and_empty_row_deletion_are_explicit():
    frame = pd.DataFrame({"city": [None, "", "  ", "Алматы"], "id": [None, None, 3, 4]})
    assert len(run(frame).processed) == 4
    assert len(run(frame, drop_empty_rows=True).processed) == 2
    result = run(frame, fill_missing={"city": "Unknown", "id": 0})
    assert result.processed["city"].tolist() == ["Unknown", "Unknown", "Unknown", "Алматы"]
    assert result.summary()["missing_after"] == 0


def test_rename_drop_select_reorder_and_sort_reference_current_names():
    frame = pd.DataFrame({"id": [2, 1], "name": ["B", "A"], "unused": [8, 9]})
    result = run(
        frame,
        rename_columns={"name": "customer"},
        drop_columns=["unused"],
        select_columns=["customer", "id"],
        reorder_columns=["id", "customer"],
        sort_by=["id"],
        sort_ascending=False,
    )
    assert result.processed.columns.tolist() == ["id", "customer"]
    assert result.processed["id"].tolist() == [2, 1]


@pytest.mark.parametrize(
    "operator,value,wanted",
    [
        ("equals", "Ann", [0]),
        ("not_equals", "Ann", [1, 2]),
        ("contains", ".", [1]),
        ("is_empty", None, [2]),
        ("is_not_empty", None, [0, 1]),
    ],
)
def test_text_filters_are_literal_and_missing_aware(operator, value, wanted):
    frame = pd.DataFrame({"name": ["Ann", "A.B", None], "id": [0, 1, 2]})
    result = run(frame, filters=[{"column": "name", "operator": operator, "value": value}])
    assert result.processed["id"].tolist() == wanted


@pytest.mark.parametrize("operator,wanted", [("greater_than", [3]), ("less_than", [1])])
def test_numeric_filters(operator, wanted):
    result = run(
        pd.DataFrame({"id": [1, 2, 3, None]}),
        filters=[{"column": "id", "operator": operator, "value": 2}],
    )
    assert result.processed["id"].tolist() == wanted


def test_all_type_conversions_preserve_nulls():
    frame = pd.DataFrame(
        {
            "integer": ["12", None],
            "float": ["1.5", None],
            "string": [12, None],
            "datetime": ["2026-10-24", None],
            "boolean": ["true", None],
        }
    )
    result = run(frame, convert_types={column: column for column in frame.columns})
    assert result.processed.loc[0, "integer"] == 12
    assert result.processed.loc[0, "float"] == 1.5
    assert result.processed.loc[0, "string"] == "12.0"
    assert result.processed.loc[0, "datetime"] == pd.Timestamp("2026-10-24")
    assert bool(result.processed.loc[0, "boolean"]) is True
    assert result.processed.iloc[1].isna().all()


@pytest.mark.parametrize(
    "value,target",
    [
        ("secret-value", "integer"),
        ("1.25", "integer"),
        ("secret-value", "datetime"),
        ("maybe", "boolean"),
    ],
)
def test_failed_type_conversion_hides_cell_values(value, target):
    frame = pd.DataFrame({"field": [value]})
    with pytest.raises(DataFlowError) as error:
        run(frame, convert_types={"field": target})
    assert value not in str(error.value)
    assert frame.loc[0, "field"] == value


@pytest.mark.parametrize(
    "options",
    [
        {"fill_missing": {"absent": 0}},
        {"drop_duplicates": True, "deduplicate_by": ["absent"]},
        {"rename_columns": {"id": "name"}},
        {"drop_columns": ["absent"]},
        {"select_columns": ["absent"]},
        {"reorder_columns": ["id"]},
        {"sort_by": ["absent"]},
        {"filters": [{"column": "name", "operator": "greater_than", "value": 2}]},
    ],
)
def test_invalid_column_references_and_comparisons_fail_without_mutation(options):
    frame = pd.DataFrame({"id": [1], "name": ["private-cell"]})
    before = frame.copy(deep=True)
    with pytest.raises(DataFlowError) as error:
        run(frame, **options)
    assert "private-cell" not in str(error.value)
    assert_frame_equal(frame, before)


def test_normalization_retains_unicode_and_rejects_collisions():
    result = run(pd.DataFrame({" Қала Атауы ": ["Алматы"]}), normalize_columns=True)
    assert result.processed.columns.tolist() == ["қала_атауы"]
    with pytest.raises(DataFlowError):
        run(pd.DataFrame({"Full Name": [1], "full_name": [2]}), normalize_columns=True)


def test_duplicate_input_columns_are_rejected():
    with pytest.raises(DataFlowError):
        run(pd.DataFrame([[1, 2]], columns=["id", "id"]))
