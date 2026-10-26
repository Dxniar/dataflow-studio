"""An OS lease keeps another desktop owner from interrupting live workspace jobs."""

import subprocess
import sys
from pathlib import Path

import pytest

from dataflow.core.errors import DataFlowError
from dataflow.services.workspace import WorkspaceStore

_COMPETE = """
import sys
from dataflow.core.errors import DataFlowError
from dataflow.services.instance import WorkspaceLease
try:
    with WorkspaceLease(sys.argv[1]):
        print("acquired")
except DataFlowError as error:
    print(str(error))
    sys.exit(2)
"""


def test_competing_process_is_rejected_then_can_acquire_after_release(tmp_path):
    from dataflow.services.instance import WorkspaceLease

    with WorkspaceLease(tmp_path):
        contender = subprocess.run(
            [sys.executable, "-c", _COMPETE, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert contender.returncode == 2, contender.stdout + contender.stderr
        assert "already open" in contender.stdout.casefold()
    released = subprocess.run(
        [sys.executable, "-c", _COMPETE, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert released.returncode == 0, released.stdout + released.stderr
    assert released.stdout.strip() == "acquired"


def test_process_exit_without_context_cleanup_releases_the_lock(tmp_path):
    from dataflow.services.instance import WorkspaceLease

    abrupt_exit = """
import os, sys
from dataflow.services.instance import WorkspaceLease
lease = WorkspaceLease(sys.argv[1])
lease.__enter__()
os._exit(0)
"""
    exited = subprocess.run(
        [sys.executable, "-c", abrupt_exit, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert exited.returncode == 0, exited.stdout + exited.stderr
    with WorkspaceLease(tmp_path):
        pass


def test_close_and_exception_exit_release_without_removing_the_lock_file(tmp_path):
    from dataflow.services.instance import WorkspaceLease

    lease = WorkspaceLease(tmp_path)
    with pytest.raises(RuntimeError, match="application failure"):
        with lease:
            raise RuntimeError("application failure")
    lease.close()
    assert lease.path.is_file()
    with WorkspaceLease(tmp_path) as second:
        second.close()
        with WorkspaceLease(tmp_path):
            pass


def test_lease_and_store_share_explicit_and_environment_directory(tmp_path, monkeypatch):
    from dataflow.services.instance import WorkspaceLease

    override = tmp_path / "override"
    monkeypatch.setenv("DATAFLOW_WORKSPACE_DIR", str(override))
    assert WorkspaceLease().path.parent == WorkspaceStore().path.parent == override
    explicit = tmp_path / "explicit"
    assert WorkspaceLease(explicit).path.parent == WorkspaceStore(explicit).path.parent == explicit
    monkeypatch.delenv("DATAFLOW_WORKSPACE_DIR")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert WorkspaceLease().path.parent == WorkspaceStore().path.parent


@pytest.mark.parametrize("operation", ["mkdir", "open"])
def test_unexpected_permission_failures_are_sanitized(tmp_path, monkeypatch, operation):
    from dataflow.services.instance import WorkspaceLease

    def denied(*args, **kwargs):
        raise PermissionError("private-path-and-system-details")

    monkeypatch.setattr(Path, operation, denied)
    with pytest.raises(DataFlowError) as error:
        with WorkspaceLease(tmp_path):
            pass
    assert "private-path" not in str(error.value)
    assert str(tmp_path) not in str(error.value)
    assert "already open" not in str(error.value).casefold()
