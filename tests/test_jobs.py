"""Cooperative control stops work at boundaries and reports bounded progress."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from dataflow.core.errors import DataFlowError


def test_cancel_from_another_thread_stops_at_next_checkpoint():
    from dataflow.core.jobs import JobCancelled, JobControl

    control = JobControl()
    control.checkpoint()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(control.cancel).result()
    assert control.cancelled
    with pytest.raises(JobCancelled) as error:
        control.checkpoint()
    assert isinstance(error.value, DataFlowError)


def test_progress_event_fraction_and_callback():
    from dataflow.core.jobs import JobControl, ProgressEvent

    events = []
    JobControl(events.append).report("read", 2, 4, "Loading file")
    assert events == [ProgressEvent("read", 2, 4, "Loading file")]
    assert events[0].fraction == 0.5
    assert ProgressEvent("read", 0, 0).fraction == 0
    assert ProgressEvent("read", 7, 4).fraction == 1


def test_fingerprint_changes_with_source_content_and_can_cancel(tmp_path):
    from dataflow.core.jobs import JobCancelled, JobControl, file_fingerprint

    path = tmp_path / "input.csv"
    path.write_bytes(b"id\n1\n")
    first = file_fingerprint(path)
    path.write_bytes(b"id\n2\n")
    second = file_fingerprint(path)
    assert first["sha256"] != second["sha256"]
    assert first["size"] == second["size"] == 5
    assert first["path"] == str(path.resolve())
    control = JobControl()
    control.cancel()
    with pytest.raises(JobCancelled):
        file_fingerprint(path, control)
