"""Safe, explicit type conversion and literal filtering; never eval/query."""

import math

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .errors import DataFlowError
from .validation import empty_mask


def convert_types(frame: pd.DataFrame, conversions: dict[str, str]) -> pd.DataFrame:
    for column, target in conversions.items():
        values = frame[column].mask(empty_mask(frame[column]))
        try:
            if target == "string":
                converted = values.astype("string")
            elif target in {"integer", "float"}:
                numeric = pd.to_numeric(values, errors="raise")
                if not numeric.dropna().map(math.isfinite).all():
                    raise ValueError("Nonfinite number")
                converted = numeric.astype("Int64" if target == "integer" else "Float64")
            elif target == "datetime":
                if is_numeric_dtype(values) and values.notna().any():
                    raise ValueError("Numeric dates need an explicit unit")
                converted = pd.to_datetime(values, errors="raise", format="mixed")
            else:
                mapping = {
                    "true": True,
                    "false": False,
                    "yes": True,
                    "no": False,
                    "1": True,
                    "0": False,
                }

                def boolean(value, mapping=mapping):
                    if pd.isna(value):
                        return pd.NA
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, (int, float)) and value in (0, 1):
                        return bool(value)
                    if isinstance(value, str) and value.strip().casefold() in mapping:
                        return mapping[value.strip().casefold()]
                    raise ValueError("Invalid boolean")

                converted = values.map(boolean).astype("boolean")
        except (ValueError, TypeError, OverflowError):
            raise DataFlowError(
                f"Cannot convert column '{column}' to {target}. Check its values and missing cells."
            ) from None
        frame[column] = converted
    return frame


def filter_rows(frame: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    for condition in filters:
        column = condition["column"]
        operator = condition["operator"]
        value = condition.get("value")
        series = frame[column]
        missing = empty_mask(series)
        try:
            if operator == "is_empty":
                mask = missing
            elif operator == "is_not_empty":
                mask = ~missing
            elif operator == "contains":
                mask = series.map(
                    lambda item, needle=value: isinstance(item, str) and needle in item
                )
            elif operator in {"greater_than", "less_than"}:
                if not is_numeric_dtype(series) or is_bool_dtype(series):
                    raise DataFlowError(
                        f"Numeric filter requires a numeric column: '{column}'. Convert its type first."
                    )
                mask = series.gt(value) if operator == "greater_than" else series.lt(value)
            else:
                equal = missing if value is None else series.eq(value).fillna(False)
                mask = equal if operator == "equals" else ~equal
        except (TypeError, ValueError):
            raise DataFlowError(f"Filter cannot compare the types in column '{column}'.") from None
        frame = frame.loc[mask.fillna(False)].copy()
    return frame
