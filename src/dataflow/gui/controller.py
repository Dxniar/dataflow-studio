"""Screen-independent GUI services and a single background-task queue."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

import pandas as pd

from dataflow.core.configuration import PipelineConfig
from dataflow.core.processor import ProcessingResult, process_frame
from dataflow.core.validation import missing_count


def run_pipeline(frame: pd.DataFrame, config_dict: dict) -> ProcessingResult:
    """Validate the GUI configuration and execute the shared core pipeline."""
    return process_frame(frame, PipelineConfig.from_dict(config_dict))


def preview_data(frame: pd.DataFrame, limit: int = 100) -> dict:
    """Prepare a bounded, display-only snapshot without changing the frame."""
    return {
        "columns": [str(column) for column in frame.columns],
        "rows": [
            [
                "—"
                if pd.isna(value) or (isinstance(value, str) and not value.strip())
                else str(value)
                for value in row
            ]
            for row in frame.head(limit).itertuples(index=False, name=None)
        ],
        "total_rows": len(frame),
        "missing": missing_count(frame),
    }


def workflow_text(config_dict: dict) -> str:
    """Show every non-default operation, including descending sorting."""
    config = PipelineConfig.from_dict(config_dict).to_dict()
    defaults = PipelineConfig().to_dict()
    active = {key: value for key, value in config.items() if value != defaults[key]}
    return (
        json.dumps(active, indent=2, ensure_ascii=False)
        if active
        else (
            "No operations selected.\n\nChoose exactly what you want to change.\nYour source files stay untouched."
        )
    )


def save_workflow(config_dict: dict, path: str | Path) -> Path:
    """Validate and serialize before opening a new workflow file."""
    content = json.dumps(
        PipelineConfig.from_dict(config_dict).to_dict(), indent=2, ensure_ascii=False
    )
    destination = Path(path)
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(content)
    return destination


@dataclass
class TaskOutcome:
    name: str
    value: Any = None
    error: Exception | None = None


class TaskRunner:
    """Run one operation at a time; the UI polls outcomes on its own thread."""

    def __init__(self):
        self.busy = False
        self._queue: Queue[TaskOutcome] = Queue()

    def submit(self, name: str, function: Callable[[], Any]) -> bool:
        if self.busy:
            return False
        self.busy = True

        def run():
            try:
                self._queue.put(TaskOutcome(name, value=function()))
            except Exception as error:  # Keep worker failures on the main-thread path.
                self._queue.put(TaskOutcome(name, error=error))

        Thread(target=run, name="dataflow-worker", daemon=True).start()
        return True

    def poll(self) -> TaskOutcome | None:
        try:
            result = self._queue.get_nowait()
        except Empty:
            return None
        self.busy = False
        return result
