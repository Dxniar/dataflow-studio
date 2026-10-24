"""Metadata-only local logging for console-free desktop launches."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_gui_logging(path: Path | None = None) -> Path:
    """Install one rotating GUI file handler; callers handle unavailable storage."""
    if path is None:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
        path = base / "DataFlowStudio" / "logs" / "dataflow.log"
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dataflow")
    for handler in logger.handlers[:]:
        if getattr(handler, "dataflow_gui_handler", False):
            logger.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.dataflow_gui_handler = True
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("Desktop metadata logging started")
    return path
