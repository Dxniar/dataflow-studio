"""An exclusive OS lease gives each local workspace one desktop owner."""

import errno
import os
from pathlib import Path

from dataflow.core.errors import DataFlowError

from .workspace import workspace_directory

_ALREADY_OPEN = "This workspace is already open. Close its other DataFlow Studio window first."
_UNAVAILABLE = "Cannot access the local workspace lock. Check folder access and try again."


class WorkspaceLease:
    """Hold a nonblocking file lock until close, context exit, or process exit.

    The lock file stays in place. Removing it would allow another process to lock
    a different inode while an existing owner still holds the original lock.
    """

    def __init__(self, directory: Path | None = None):
        self.path = workspace_directory(directory) / "workspace.lock"
        self._stream = None

    def __enter__(self):
        if self._stream is not None:
            raise DataFlowError(_ALREADY_OPEN)
        stream = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            stream = self.path.open("a+b", buffering=0)
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise DataFlowError(_ALREADY_OPEN) from None
                raise
            self._stream = stream
            return self
        except DataFlowError:
            if stream is not None:
                stream.close()
            raise
        except (OSError, ValueError):
            if stream is not None:
                stream.close()
            raise DataFlowError(_UNAVAILABLE) from None

    def close(self) -> None:
        """Closing the owning descriptor releases its OS lock on both platforms."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.close()
            except OSError:
                raise DataFlowError("Cannot release the local workspace lock.") from None

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
