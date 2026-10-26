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


def test_transform_progress_counts_only_requested_operations():
    from dataflow.core.jobs import JobControl

    events = []
    result = process_frame(
        pd.DataFrame({"id": [" 2 ", " 1 "]}),
        PipelineConfig(trim_whitespace=True, sort_by=["id"]),
        control=JobControl(events.append),
    )
    assert result.processed["id"].tolist() == ["1", "2"]
    transforms = [event for event in events if event.stage == "transform"]
    assert [(event.completed, event.total) for event in transforms] == [(0, 2), (1, 2), (2, 2)]


def test_cancellation_between_transforms_preserves_input():
    from dataflow.core.jobs import JobCancelled, JobControl

    frame = pd.DataFrame({"id": [" 2 ", " 1 "]})
    before = frame.copy(deep=True)
    events = []

    def report(event):
        events.append(event)
        if event.stage == "transform" and event.completed == 1:
            control.cancel()

    control = JobControl(report)
    with pytest.raises(JobCancelled):
        process_frame(frame, PipelineConfig(trim_whitespace=True, sort_by=["id"]), control=control)
    assert max(event.completed for event in events) == 1
    assert_frame_equal(frame, before)


def test_cancelled_batch_retains_published_success_and_checkpoint(tmp_path):
    from dataflow.core.jobs import JobControl
    from dataflow.core.processor import BatchResult, batch_process

    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    first.write_text("id\n1\n", encoding="utf-8")
    second.write_text("id\n2\n", encoding="utf-8")
    snapshots = []
    control = JobControl()

    def checkpoint(result):
        snapshots.append(result.to_dict())
        if result.successes:
            control.cancel()

    result = batch_process(
        [first, second],
        PipelineConfig(),
        tmp_path / "out",
        control=control,
        checkpoint_callback=checkpoint,
    )
    assert len(result.successes) == 1
    assert result.errors == []
    assert result.pending == [str(second)]
    assert result.cancelled
    output = tmp_path / "out" / "first_processed.csv"
    assert output.is_file()
    assert not (tmp_path / "out" / "second_processed.csv").exists()
    assert BatchResult.from_dict(snapshots[-1]).to_dict() == result.to_dict()


def test_batch_retry_processes_only_errors_and_pending_using_current_contents(tmp_path):
    from dataflow.core.processor import BatchResult, batch_process

    first, failed, pending = [tmp_path / name for name in ("first.csv", "bad.csv", "later.csv")]
    first.write_text("id\n1\n", encoding="utf-8")
    failed.write_text("broken", encoding="utf-8")
    pending.write_text("id\n3\n", encoding="utf-8")
    previous = batch_process([first, failed], PipelineConfig(sort_by=["id"]), tmp_path / "out")
    assert len(previous.successes) == len(previous.errors) == 1
    previous.pending = [str(pending)]
    previous.cancelled = True
    old_output = tmp_path / "out" / "first_processed.csv"
    old_bytes = old_output.read_bytes()
    first.unlink()  # A published success must not be reopened on retry.
    failed.write_text("id\n9\n", encoding="utf-8")
    snapshots = []
    resumed = batch_process(
        [first, failed, pending],
        PipelineConfig(sort_by=["id"]),
        tmp_path / "out",
        resume_from=previous.to_dict(),
        checkpoint_callback=lambda result: snapshots.append(result.to_dict()),
    )
    assert len(resumed.successes) == 3
    assert resumed.errors == []
    assert resumed.pending == []
    assert not resumed.cancelled
    assert old_output.read_bytes() == old_bytes
    assert not (tmp_path / "out" / "first_processed_1.csv").exists()
    assert pd.read_csv(tmp_path / "out" / "bad_processed.csv")["id"].tolist() == [9]
    assert BatchResult.from_dict(snapshots[0]).pending == [str(pending)]
    assert resumed.summary() == {"processed": 3, "failed": 0, "files": 3}


def test_batch_duplicate_input_is_processed_once(tmp_path):
    from dataflow.core.processor import batch_process

    source = tmp_path / "input.csv"
    source.write_text("id\n1\n", encoding="utf-8")
    result = batch_process([source, str(source.resolve())], PipelineConfig(), tmp_path / "out")
    assert result.summary() == {"processed": 1, "failed": 0, "files": 1}
    assert len(list((tmp_path / "out").glob("*.csv"))) == 1


@pytest.mark.parametrize(
    "payload", [None, {}, {"successes": "bad"}, {"successes": [{"input": "x"}]}]
)
def test_batch_checkpoint_rejects_malformed_state(payload):
    from dataflow.core.processor import BatchResult

    with pytest.raises(DataFlowError):
        BatchResult.from_dict(payload)


def test_process_and_merge_forward_explicit_import_schema(tmp_path):
    from dataflow.core.processor import merge_files, process_file

    paths = [tmp_path / "a.csv", tmp_path / "b.csv"]
    for path in paths:
        path.write_text("id\n001\n", encoding="utf-8")
    options = {"column_types": {"id": "string"}}
    assert process_file(paths[0], PipelineConfig(), import_options=options).processed[
        "id"
    ].tolist() == ["001"]
    assert merge_files(paths, import_options=options).processed["id"].tolist() == ["001", "001"]


def test_batch_cancel_immediately_after_atomic_publication_keeps_success(tmp_path, monkeypatch):
    import os

    from dataflow.core import io
    from dataflow.core.jobs import JobControl
    from dataflow.core.processor import batch_process

    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    first.write_bytes(b"id\n1\n")
    second.write_bytes(b"id\n2\n")
    control = JobControl()
    publish = os.rename if os.name == "nt" else os.link

    def cancel_after_publish(source, destination):
        publish(source, destination)
        control.cancel()

    monkeypatch.setattr(io.os, "rename" if os.name == "nt" else "link", cancel_after_publish)
    result = batch_process([first, second], PipelineConfig(), tmp_path / "out", control=control)
    assert len(result.successes) == 1
    assert result.errors == []
    assert result.pending == [str(second)]
    assert result.cancelled
    assert pd.read_csv(result.successes[0]["output"])["id"].tolist() == [1]


def test_precancelled_batch_has_only_pending_files_and_one_checkpoint(tmp_path):
    from dataflow.core.jobs import JobControl
    from dataflow.core.processor import batch_process

    source = tmp_path / "not-opened.csv"
    control = JobControl()
    control.cancel()
    snapshots = []
    result = batch_process(
        [source],
        PipelineConfig(),
        tmp_path / "out",
        control=control,
        checkpoint_callback=snapshots.append,
    )
    assert result.errors == result.successes == []
    assert result.pending == [str(source)]
    assert result.cancelled
    assert len(snapshots) == 1
    assert snapshots[0].to_dict() == result.to_dict()


def test_merge_cancels_between_files_before_missing_second_input(tmp_path):
    from dataflow.core.jobs import JobCancelled, JobControl
    from dataflow.core.processor import merge_files

    first = tmp_path / "first.csv"
    first.write_bytes(b"id\n1\n")

    def report(event):
        if event.stage == "read" and event.total == 2 and event.completed == 1:
            control.cancel()

    control = JobControl(report)
    with pytest.raises(JobCancelled):
        merge_files([first, tmp_path / "never-opened.csv"], control=control)


def test_batch_checkpoint_snapshots_are_independent_after_later_files(tmp_path):
    from dataflow.core.processor import batch_process

    first, second = tmp_path / "one.csv", tmp_path / "two.csv"
    first.write_bytes(b"id\n1\n")
    second.write_bytes(b"id\n2\n")
    snapshots = []
    result = batch_process(
        [first, second], PipelineConfig(), tmp_path / "out", checkpoint_callback=snapshots.append
    )
    assert len(result.successes) == 2
    assert len(snapshots[0].successes) == 1
    assert snapshots[0].pending == [str(second)]
    assert snapshots[1].pending == []
    snapshots[0].successes[0]["summary"]["operations"].append("external mutation")
    assert result.successes[0]["summary"]["operations"] == []


def test_file_reports_read_completion_before_transform_start(tmp_path):
    from dataflow.core.jobs import JobControl
    from dataflow.core.processor import process_file

    source = tmp_path / "input.csv"
    source.write_bytes(b"id\n 1 \n")
    events = []
    process_file(source, PipelineConfig(trim_whitespace=True), control=JobControl(events.append))
    first_transform = next(
        index for index, event in enumerate(events) if event.stage == "transform"
    )
    assert any(
        event.stage == "read" and event.completed == event.total == 1
        for event in events[:first_transform]
    )


def test_resume_protects_original_sources_from_prior_successes(tmp_path):
    from dataflow.core.processor import batch_process

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    protected = output_dir / "input_processed.csv"
    protected.write_bytes(b"id\n7\n")
    previous = batch_process([protected], PipelineConfig(), tmp_path / "prior-out")
    source = tmp_path / "input.csv"
    source.write_bytes(b"id\n1\n")
    previous.pending = [str(source)]
    resumed = batch_process([source], PipelineConfig(), output_dir, resume_from=previous.to_dict())
    assert len(resumed.successes) == 1
    assert len(resumed.errors) == 1
    assert "original input" in resumed.errors[0]["error"]
    assert protected.read_bytes() == b"id\n7\n"
