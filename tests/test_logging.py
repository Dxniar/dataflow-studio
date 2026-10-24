"""Metadata logging is observable in GUI launches without a console."""

import logging

import pandas as pd

from dataflow.core.configuration import PipelineConfig
from dataflow.core.processor import process_frame


def test_gui_log_records_metadata_without_table_cells(tmp_path):
    from dataflow.utils.logging_config import configure_gui_logging

    logger = logging.getLogger("dataflow")
    original_handlers, original_level, original_propagate = (
        logger.handlers[:],
        logger.level,
        logger.propagate,
    )
    try:
        path = configure_gui_logging(tmp_path / "logs" / "session.log")
        process_frame(pd.DataFrame({"name": ["PRIVATE-CELL-VALUE"]}), PipelineConfig())
        for handler in logger.handlers:
            handler.flush()
        content = path.read_text(encoding="utf-8")
        assert "before=1 after=1" in content
        assert "PRIVATE-CELL-VALUE" not in content
        logger.setLevel(logging.ERROR)
        logging.getLogger("dataflow.core").info("suppressed-info")
        for handler in logger.handlers:
            handler.flush()
        assert "suppressed-info" not in path.read_text(encoding="utf-8")
    finally:
        for handler in logger.handlers:
            if handler not in original_handlers:
                handler.close()
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate
