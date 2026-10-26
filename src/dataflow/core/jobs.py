"""Thread-safe cooperative cancellation and metadata-only progress reporting."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from .errors import DataFlowError


class JobCancelled(DataFlowError):
    """The user requested cancellation before the next work boundary."""


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    completed: int
    total: int
    message: str = ""

    @property
    def fraction(self) -> float:
        return min(1.0, max(0.0, self.completed / self.total)) if self.total > 0 else 0.0


class JobControl:
    def __init__(self, progress_callback: Callable[[ProgressEvent], None] | None = None):
        self._cancelled = Event()
        self._progress_callback = progress_callback

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()

    def checkpoint(self) -> None:
        if self.cancelled:
            raise JobCancelled("Job cancelled. Completed output files have been preserved.")

    def report(self, stage: str, completed: int, total: int, message: str = "") -> None:
        if self._progress_callback is not None:
            self._progress_callback(ProgressEvent(stage, completed, total, message))


def file_fingerprint(path: str | Path, control: JobControl | None = None) -> dict:
    """Hash a source in bounded chunks; persist metadata rather than table contents."""
    try:
        if control is not None:
            control.checkpoint()
        source = Path(path).expanduser().resolve()
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            metadata = source.stat()
            while chunk := stream.read(1024 * 1024):
                if control is not None:
                    control.checkpoint()
                digest.update(chunk)
        if control is not None:
            control.checkpoint()
        return {
            "path": str(source),
            "size": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns,
            "sha256": digest.hexdigest(),
        }
    except DataFlowError:
        raise
    except (OSError, TypeError, RuntimeError):
        raise DataFlowError(
            "Cannot read file metadata. Check the source file and access."
        ) from None
