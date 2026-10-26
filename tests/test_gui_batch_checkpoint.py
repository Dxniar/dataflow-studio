"""Every worker starts with durable pending inputs and inherited successes."""

from types import SimpleNamespace

from dataflow.gui.app import DataFlowApp
from dataflow.gui.workspace import DesktopWorkspace


def _payload(tmp_path):
    return {
        "paths": [str(tmp_path / "done.csv"), str(tmp_path / "pending.csv")],
        "config": {},
        "output_dir": str(tmp_path / "out"),
        "io_options": {"encoding": "utf-8-sig", "delimiter": ","},
        "output_format": "csv",
        "sheet": 0,
        "collision": "error",
    }


def test_recovery_inherits_durable_checkpoint_before_worker_submission(tmp_path):
    workspace = DesktopWorkspace(tmp_path / "workspace")
    payload = _payload(tmp_path)
    inherited = {
        "successes": [
            {
                "input": payload["paths"][0],
                "output": str(tmp_path / "out" / "done_processed.csv"),
                "summary": {},
            }
        ],
        "errors": [],
        "pending": [payload["paths"][1]],
        "cancelled": False,
    }
    app = SimpleNamespace(busy=False, workspace=workspace)

    def submit(name, work, finish, **kwargs):
        job = workspace.get_job(kwargs["job_id"])
        assert job["checkpoint"] == inherited
        # A process exit at this exact point must still retain the successful file.
        reopened = DesktopWorkspace(tmp_path / "workspace")
        assert reopened.get_job(job["id"])["checkpoint"]["successes"] == inherited["successes"]
        return True

    app._submit = submit
    assert DataFlowApp._begin_batch(app, payload, resume_from=inherited)


def test_new_batch_has_durable_pending_inputs_before_worker_submission(tmp_path):
    workspace = DesktopWorkspace(tmp_path / "workspace")
    payload = _payload(tmp_path)
    app = SimpleNamespace(busy=False, workspace=workspace)

    def submit(name, work, finish, **kwargs):
        job = workspace.get_job(kwargs["job_id"])
        assert job["checkpoint"] == {
            "successes": [],
            "errors": [],
            "pending": payload["paths"],
            "cancelled": False,
        }
        return True

    app._submit = submit
    assert DataFlowApp._begin_batch(app, payload)
