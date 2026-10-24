"""Small opt-in cleaning operations. Caller supplies an owned working copy."""

import pandas as pd

from .validation import empty_mask


def trim_whitespace(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.map(lambda value: value.strip() if isinstance(value, str) else value)


def drop_empty_rows(frame: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame({column: empty_mask(frame[column]) for column in frame.columns})
    return frame.loc[~empty.all(axis=1)].copy()


def fill_missing(frame: pd.DataFrame, values: dict) -> pd.DataFrame:
    for column, value in values.items():
        mask = empty_mask(frame[column])
        if mask.any():
            # Object permits a text fallback for a numeric column without silent truncation.
            filled = frame[column].astype(object).copy()
            filled.loc[mask] = value
            frame[column] = filled.infer_objects(copy=False)
    return frame


def standardize_values(frame: pd.DataFrame, mappings: dict) -> pd.DataFrame:
    for column, mapping in mappings.items():
        frame[column] = frame[column].map(
            lambda value, replacements=mapping: (
                replacements.get(value, value) if isinstance(value, str) else value
            )
        )
    return frame
