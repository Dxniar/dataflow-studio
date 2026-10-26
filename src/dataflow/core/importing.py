"""Explicit, strictly validated import schemas and loss-aware conversions."""

import copy
import json
import math
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .configuration import TYPE_NAMES, _mapping, _unique_object
from .errors import DataFlowError
from .validation import empty_mask


def _read_json(path: str | Path, label: str) -> dict:
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object
        )
    except DataFlowError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError):
        raise DataFlowError(f"Cannot read {label}. Use a valid UTF-8 JSON file.") from None


@dataclass
class ImportOptions:
    """Safety limits bound imports; they are not supported-size performance claims."""

    column_types: dict[str, str] = field(default_factory=dict)
    date_formats: dict[str, str] = field(default_factory=dict)
    decimal: str = "."
    thousands: str | None = None
    max_file_mb: int = 50
    max_table_mb: int = 64
    max_rows: int = 500_000
    max_cells: int = 2_000_000

    def __post_init__(self) -> None:
        _mapping(self.column_types, "column_types")
        _mapping(self.date_formats, "date_formats")
        if any(
            not isinstance(kind, str) or kind not in TYPE_NAMES
            for kind in self.column_types.values()
        ):
            raise DataFlowError("Import types support string, integer, float, datetime, boolean.")
        if any(
            self.column_types.get(name) != "datetime" or not isinstance(fmt, str) or not fmt.strip()
            for name, fmt in self.date_formats.items()
        ):
            raise DataFlowError("Date formats require a datetime column and a nonempty format.")
        for value, label in ((self.decimal, "decimal"), (self.thousands, "thousands")):
            if value is None and label == "thousands":
                continue
            if not isinstance(value, str) or len(value) != 1 or value in "0123456789+-eE\r\n\x00":
                raise DataFlowError(f"Import {label} must be one separator character.")
        if self.decimal == self.thousands:
            raise DataFlowError("Decimal and thousands separators must differ.")
        for label in ("max_file_mb", "max_table_mb", "max_rows", "max_cells"):
            value = getattr(self, label)
            if type(value) is not int or value <= 0:
                raise DataFlowError(f"Import {label} must be a positive integer.")
        self.column_types = copy.deepcopy(self.column_types)
        self.date_formats = copy.deepcopy(self.date_formats)

    @classmethod
    def from_dict(cls, data: dict) -> "ImportOptions":
        if not isinstance(data, dict) or set(data) - {item.name for item in fields(cls)}:
            raise DataFlowError("Import options must be an object with recognized fields.")
        return cls(**copy.deepcopy(data))

    @classmethod
    def from_json(cls, path: str | Path) -> "ImportOptions":
        return cls.from_dict(_read_json(path, "import options"))

    def to_dict(self) -> dict:
        return asdict(self)


def _number(value, options: ImportOptions) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric identifier")
    if not isinstance(value, str):
        number = Decimal(str(value))
    else:
        text = value.strip()
        integer = r"\d+"
        if options.thousands:
            group = re.escape(options.thousands)
            integer = rf"(?:\d+|\d{{1,3}}(?:{group}\d{{3}})+)"
        decimal = re.escape(options.decimal)
        if not re.fullmatch(
            rf"[+-]?(?:{integer}(?:{decimal}\d*)?|{decimal}\d+)(?:[eE][+-]?\d+)?", text
        ):
            raise ValueError("Invalid numeric text")
        if options.thousands:
            text = text.replace(options.thousands, "")
        number = Decimal(text.replace(options.decimal, "."))
    if not number.is_finite():
        raise ValueError("Nonfinite number")
    return number


def apply_import_schema(
    frame: pd.DataFrame, options: ImportOptions, *, control=None
) -> pd.DataFrame:
    """Convert after lexical reading, without ever exposing rejected cell contents."""
    missing = set(options.column_types) - set(frame.columns)
    if missing:
        raise DataFlowError("Import schema references a missing column. Check the source header.")
    for column, kind in options.column_types.items():
        if control is not None:
            control.checkpoint()
        values = frame[column]
        try:
            if kind == "string":
                converted = values.astype("string")
            else:
                values = values.mask(empty_mask(values))
                if kind in {"integer", "float"}:

                    def numeric(value, kind=kind):
                        if pd.isna(value):
                            return pd.NA
                        number = _number(value, options)
                        if kind == "integer":
                            if (
                                number != number.to_integral_value()
                                or not -(2**63) <= number < 2**63
                            ):
                                raise ValueError("Not a signed 64-bit integer")
                            return int(number)
                        result = float(number)
                        if not math.isfinite(result):
                            raise ValueError("Float overflow")
                        return result

                    converted = values.map(numeric).astype(
                        "Int64" if kind == "integer" else "Float64"
                    )
                elif kind == "datetime":
                    fmt = options.date_formats.get(column)

                    def timestamp(value, fmt=fmt):
                        if pd.isna(value):
                            return pd.NaT
                        if isinstance(value, (date, datetime, pd.Timestamp)):
                            return pd.Timestamp(value)
                        if not isinstance(value, str):
                            raise ValueError("Numeric dates need an explicit unit")
                        result = pd.to_datetime(value, format=fmt or "ISO8601", errors="raise")
                        if pd.isna(result):
                            raise ValueError("Nonempty date text cannot become missing")
                        return result

                    converted = pd.to_datetime(values.map(timestamp), errors="raise")
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
                        key = str(value).strip().casefold()
                        if key not in mapping:
                            raise ValueError("Invalid boolean")
                        return mapping[key]

                    converted = values.map(boolean).astype("boolean")
        except (ValueError, TypeError, OverflowError, ArithmeticError):
            raise DataFlowError(
                f"Cannot convert import column '{column}' to {kind}. Check its type, format, and missing cells."
            ) from None
        frame[column] = converted
    return frame
