"""Errors safe to show in GUI dialogs, the terminal, and metadata-only logs."""


class DataFlowError(ValueError):
    """An expected validation, processing, or file operation failure."""
