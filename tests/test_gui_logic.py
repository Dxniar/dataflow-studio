"""Headless contracts for the desktop adapter; no Tk root is created."""

import time

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from dataflow.core.configuration import PipelineConfig
from dataflow.core.errors import DataFlowError
from dataflow.core.processor import process_frame
from dataflow.gui.controller import TaskRunner, preview_data, run_pipeline


def test_gui_pipeline_matches_shared_engine_and_preserves_original():
    source = pd.DataFrame({"name": ["  Әлия ", "  Әлия ", "Ben"], "amount": [1, 1, 2]})
    original = source.copy(deep=True)
    config = {"trim_whitespace": True, "drop_duplicates": True, "sort_by": ["amount"]}
    result = run_pipeline(source, config)
    expected = process_frame(source, PipelineConfig.from_dict(config))
    assert_frame_equal(result.processed, expected.processed)
    assert result.processed["name"].tolist() == ["Әлия", "Ben"]
    assert result.duplicates_removed == 1
    assert_frame_equal(source, original)


def test_gui_pipeline_rejects_invalid_configuration_without_mutation():
    source = pd.DataFrame({"name": ["A"]})
    with pytest.raises(DataFlowError):
        run_pipeline(source, {"drop_everything": True})
    assert source.to_dict("list") == {"name": ["A"]}


def test_preview_is_bounded_and_preserves_missing_metadata():
    source = pd.DataFrame({"name": [None, "Әлия"] + ["Person"] * 200})
    preview = preview_data(source, limit=3)
    assert preview["total_rows"] == 202
    assert preview["missing"] == 1
    assert preview["columns"] == ["name"]
    assert preview["rows"] == [["—"], ["Әлия"], ["Person"]]


def test_preview_handles_empty_frame():
    preview = preview_data(pd.DataFrame(columns=["id"]))
    assert preview["rows"] == []
    assert preview["total_rows"] == 0
    assert preview["columns"] == ["id"]


def test_preview_counts_blank_cells_like_the_pipeline():
    source = pd.DataFrame({"name": [None, "", "  ", "Әлия"]})
    preview = preview_data(source)
    assert preview["missing"] == 3
    assert preview["rows"] == [["—"], ["—"], ["—"], ["Әлия"]]


def test_workflow_preview_shows_descending_sort_and_selected_operations():
    import json

    from dataflow.gui.controller import workflow_text

    visible = json.loads(
        workflow_text({"trim_whitespace": True, "sort_by": ["id"], "sort_ascending": False})
    )
    assert visible == {"trim_whitespace": True, "sort_by": ["id"], "sort_ascending": False}


def test_save_workflow_validates_before_creating_output(tmp_path):
    from dataflow.gui.controller import save_workflow

    destination = tmp_path / "invalid.json"
    with pytest.raises(DataFlowError):
        save_workflow({"rename_columns": {"id": ""}}, destination)
    assert not destination.exists()


def test_save_workflow_round_trip_and_no_overwrite(tmp_path):
    from dataflow.gui.controller import save_workflow

    destination = tmp_path / "workflow.json"
    save_workflow({"trim_whitespace": True}, destination)
    assert PipelineConfig.from_json(destination).trim_whitespace
    original = destination.read_bytes()
    with pytest.raises(FileExistsError):
        save_workflow({}, destination)
    assert destination.read_bytes() == original


def _wait_outcome(runner):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        outcome = runner.poll()
        if outcome is not None:
            return outcome
        time.sleep(0.01)
    pytest.fail("Background task failed to return within 3 seconds")


def test_worker_delivers_success_and_blocks_duplicate_until_consumed():
    runner = TaskRunner()
    assert runner.submit("count", lambda: 7)
    assert not runner.submit("duplicate", lambda: 9)
    outcome = _wait_outcome(runner)
    assert outcome.value == 7
    assert outcome.error is None
    assert not runner.busy


def test_worker_reports_error_and_allows_next_operation():
    runner = TaskRunner()

    def fail():
        raise ValueError("Invalid operation")

    runner.submit("bad", fail)
    outcome = _wait_outcome(runner)
    assert isinstance(outcome.error, ValueError)
    assert runner.submit("retry", lambda: "done")
    assert _wait_outcome(runner).value == "done"
