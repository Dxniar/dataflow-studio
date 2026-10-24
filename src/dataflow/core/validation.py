"""Column and missing-data validation shared by files and transformations."""

import re
import unicodedata
from collections.abc import Iterable

import pandas as pd

from .errors import DataFlowError


def validate_columns(columns: Iterable) -> list[str]:
    names = list(columns)
    if not names:
        raise DataFlowError("The table has no columns. A header row is required.")
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise DataFlowError("Column headers must be nonempty text.")
    if len(names) != len(set(names)):
        raise DataFlowError(
            "Duplicate column headers are not supported. Give each column a unique name."
        )
    return names


def require_columns(frame: pd.DataFrame, columns: Iterable[str], operation: str) -> None:
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise DataFlowError(f"{operation}: missing column(s): {', '.join(missing)}.")


def empty_mask(series: pd.Series) -> pd.Series:
    """A missing cell is null, an empty string, or whitespace-only text."""
    return series.isna() | series.map(lambda value: isinstance(value, str) and not value.strip())


def missing_count(frame: pd.DataFrame) -> int:
    return sum(int(empty_mask(frame[column]).sum()) for column in frame.columns)


def normalized_columns(columns: Iterable[str]) -> list[str]:
    names = [
        re.sub(r"[^\w]+", "_", unicodedata.normalize("NFKC", name).strip().lower()).strip("_")
        for name in columns
    ]
    try:
        return validate_columns(names)
    except DataFlowError:
        raise DataFlowError(
            "Normalizing columns produces empty or duplicate names. Rename them first."
        ) from None
