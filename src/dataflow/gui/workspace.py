"""Desktop persistence adapter. Storage failures never discard finished work."""

import logging

from dataflow.core.errors import DataFlowError
from dataflow.core.processor import BatchResult
from dataflow.services.workspace import WorkspaceStore

logger = logging.getLogger(__name__)


class CheckpointSaveError(DataFlowError):
    """A batch must stop because its newest file outcome is not durable."""


def batch_checkpoint(job):
    """Validate persisted run metadata before any list rendering or replay."""
    try:
        payload = job.get("payload") or {}
        raw = job.get("checkpoint")
        if raw is None:
            raw = payload.get("resume_from")
        if raw is None:
            raw = {
                "successes": [],
                "errors": [],
                "pending": payload.get("paths", []),
                "cancelled": False,
            }
        return BatchResult.from_dict(raw).to_dict()
    except (ValueError, TypeError, AttributeError):
        return None


class _History(list):
    def __init__(self, workspace, events):
        super().__init__(events)
        self.workspace = workspace

    def append(self, event):
        super().append(event)
        self.workspace._call(
            "append_history", event["action"], event["detail"], timestamp=event["time"]
        )
        if len(self) > 200:
            del self[:-200]


class DesktopWorkspace:
    """Retain only preferences, validated configurations, paths and run metadata."""

    def __init__(self, directory=None):
        self.store = WorkspaceStore(directory)
        self.unsafe_jobs = set()
        self.warning = self.store.warning
        self.state = self._call("load_workspace", fallback={})
        self.history = _History(self, list(reversed(self._call("history", fallback=[]))))

    @property
    def path(self):
        return self.store.path

    def _call(self, method, *args, fallback=None, **kwargs):
        try:
            value = getattr(self.store, method)(*args, **kwargs)
            if self.store.warning:
                self.warning = self.store.warning
            return value
        except (DataFlowError, OSError) as error:
            self.warning = "Local workspace is unavailable. This session remains usable; changes may not be saved."
            logger.warning("Workspace persistence failed (%s)", type(error).__name__)
            return fallback

    def save(self, payload):
        self._call("save_workspace", payload)

    def create_job(self, kind, payload):
        return self._call("create_job", kind, payload)

    def update_job(self, job_id, status, *, checkpoint=None, error=None):
        if not job_id:
            return False
        failed = object()
        result = self._call(
            "update_job", job_id, status, checkpoint=checkpoint, error=error, fallback=failed
        )
        return result is not failed

    def get_job(self, job_id):
        return self._call("get_job", job_id) if job_id else None

    def list_jobs(self):
        return self._call("list_jobs", fallback=[])
