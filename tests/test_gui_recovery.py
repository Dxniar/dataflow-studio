from types import SimpleNamespace

from dataflow.gui.app import DataFlowApp
from dataflow.gui.workspace import DesktopWorkspace


def _record(workspace, status):
    payload = {"paths": ["source.csv"], "collision": "unique"}
    job = workspace.create_job("batch", payload)
    workspace.update_job(
        job,
        status,
        checkpoint={"successes": [], "errors": [], "pending": ["source.csv"], "cancelled": False},
    )
    return job


def test_interrupted_recovery_uses_new_persisted_fail_closed_job(tmp_path):
    workspace = DesktopWorkspace(tmp_path)
    job = _record(workspace, "interrupted")
    calls = []
    app = SimpleNamespace(
        workspace=workspace,
        last_batch_job_id=job,
        fail=lambda error: None,
        _begin_batch=lambda payload, **kw: calls.append((payload, kw)) or True,
    )
    assert DataFlowApp.retry_batch(app)
    assert calls[0][0]["collision"] == "error"
    assert calls[0][1].get("job_id") is None
    assert workspace.get_job(job)["payload"]["collision"] == "unique"


def test_explicit_retry_of_checkpointed_cancelled_batch_keeps_saved_policy(tmp_path):
    workspace = DesktopWorkspace(tmp_path)
    job = _record(workspace, "cancelled")
    calls = []
    app = SimpleNamespace(
        workspace=workspace,
        last_batch_job_id=job,
        fail=lambda error: None,
        _begin_batch=lambda payload, **kw: calls.append((payload, kw)) or True,
    )
    assert DataFlowApp.retry_batch(app)
    assert calls[0][0]["collision"] == "unique"
    assert calls[0][1]["job_id"] == job
