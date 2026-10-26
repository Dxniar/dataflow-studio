from types import SimpleNamespace

import pytest

from dataflow.core.errors import DataFlowError
from dataflow.core.jobs import JobControl
from dataflow.gui.app import DataFlowApp
from dataflow.gui.workspace import DesktopWorkspace


def test_workspace_updates_report_success_or_failure(tmp_path, monkeypatch):
    workspace = DesktopWorkspace(tmp_path)
    job = workspace.create_job("batch", {"paths": ["a.csv"]})
    assert workspace.update_job(job, "running") is True

    def unavailable(*args, **kwargs):
        raise DataFlowError("Local workspace operation failed.")

    monkeypatch.setattr(workspace.store, "update_job", unavailable)
    assert workspace.update_job(job, "running") is False
    assert workspace.warning


def test_failed_checkpoint_halts_after_first_output_and_forces_safe_retry(tmp_path, monkeypatch):
    from dataflow.gui.workspace import CheckpointSaveError

    inputs = [tmp_path / "a.csv", tmp_path / "b.csv"]
    for source in inputs:
        source.write_text("id,name\n001,Alice\n", encoding="utf-8")
    workspace = DesktopWorkspace(tmp_path / "state")
    submitted = {}
    app = SimpleNamespace(
        workspace=workspace,
        runner=SimpleNamespace(control=JobControl()),
        busy=False,
        fail=lambda error: pytest.fail(str(error)),
        last_batch_job_id=None,
    )
    app._submit = lambda name, work, finish, **kwargs: submitted.update(work=work, **kwargs) or True
    payload = {
        "paths": [str(path) for path in inputs],
        "config": {},
        "output_dir": str(tmp_path / "out"),
        "output_format": "csv",
        "sheet": 0,
        "collision": "unique",
        "io_options": {"encoding": "utf-8", "delimiter": ","},
        "import_options": {},
    }
    assert DataFlowApp._begin_batch(app, payload)
    original = workspace.store.update_job

    def fail_after_publication(job_id, status, *, checkpoint=None, error=None):
        if checkpoint and checkpoint["successes"]:
            raise DataFlowError("Local workspace operation failed.")
        return original(job_id, status, checkpoint=checkpoint, error=error)

    monkeypatch.setattr(workspace.store, "update_job", fail_after_publication)
    with pytest.raises(CheckpointSaveError):
        submitted["work"]()
    assert len(list((tmp_path / "out").glob("*.csv"))) == 1
    assert submitted["job_id"] in workspace.unsafe_jobs
    calls = []
    app._begin_batch = lambda saved, **kwargs: calls.append((saved, kwargs)) or True
    assert DataFlowApp.retry_batch(app)
    assert calls[0][0]["collision"] == "error"
    assert calls[0][1].get("job_id") is None


def test_unavailable_store_rejects_batch_before_submitting_work(tmp_path):
    import sqlite3

    with sqlite3.connect(tmp_path / "workspace.sqlite3") as connection:
        connection.execute("PRAGMA user_version=999")
    workspace = DesktopWorkspace(tmp_path)
    errors = []
    app = SimpleNamespace(
        workspace=workspace,
        busy=False,
        fail=errors.append,
        _submit=lambda *args, **kwargs: pytest.fail("Worker started without durable state"),
    )
    payload = {
        "paths": ["source.csv"],
        "config": {},
        "output_dir": str(tmp_path / "out"),
        "output_format": "csv",
        "sheet": 0,
        "collision": "unique",
        "io_options": {},
        "import_options": {},
    }
    assert DataFlowApp._begin_batch(app, payload) is False
    assert errors
    assert not (tmp_path / "out").exists()
