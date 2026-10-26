"""Read-only source validation with metadata-only issue diagnostics."""

import copy
import math
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from .configuration import _mapping, _names, _scalar
from .errors import DataFlowError
from .importing import _read_json
from .validation import empty_mask, validate_columns


def _date_bound(value) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError("Dates must be ISO text")
    # fromisoformat rejects locale-specific and ambiguous date strings.
    return pd.Timestamp(datetime.fromisoformat(value))


@dataclass
class ValidationRules:
    required_columns: list[str] = field(default_factory=list)
    required_values: list[str] = field(default_factory=list)
    unique_columns: list[str] = field(default_factory=list)
    allowed_values: dict[str, list] = field(default_factory=dict)
    numeric_ranges: dict[str, dict] = field(default_factory=dict)
    date_ranges: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("required_columns", "required_values", "unique_columns"):
            _names(getattr(self, name), name)
        for name in ("allowed_values", "numeric_ranges", "date_ranges"):
            _mapping(getattr(self, name), name)
        if any(
            not isinstance(values, list) or any(not _scalar(value) for value in values)
            for values in self.allowed_values.values()
        ):
            raise DataFlowError("Allowed values must be lists of finite JSON scalars.")
        for label in ("numeric_ranges", "date_ranges"):
            for bounds in getattr(self, label).values():
                if not isinstance(bounds, dict) or set(bounds) - {"min", "max"}:
                    raise DataFlowError("Range rules accept only optional min and max bounds.")
                try:
                    values = {}
                    for key, value in bounds.items():
                        if label == "numeric_ranges":
                            if type(value) not in (int, float) or not math.isfinite(value):
                                raise ValueError("Numeric bounds must be finite")
                            values[key] = value
                        else:
                            values[key] = _date_bound(value)
                    if "min" in values and "max" in values and values["min"] > values["max"]:
                        raise ValueError("Reversed range")
                except (ValueError, TypeError, OverflowError):
                    raise DataFlowError(
                        "Invalid range bounds. Use finite numbers or ISO dates, with min <= max."
                    ) from None
        for item in fields(self):
            setattr(self, item.name, copy.deepcopy(getattr(self, item.name)))

    @classmethod
    def from_dict(cls, data: dict) -> "ValidationRules":
        if not isinstance(data, dict) or set(data) - {item.name for item in fields(cls)}:
            raise DataFlowError("Validation rules must be an object with recognized fields.")
        return cls(**copy.deepcopy(data))

    @classmethod
    def from_json(cls, path) -> "ValidationRules":
        return cls.from_dict(_read_json(path, "validation rules"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    rows: int
    issues: pd.DataFrame
    problem_rows: pd.DataFrame
    schema_errors: list[str]
    source_record_column: str
    reasons_column: str

    def summary(self) -> dict:
        return {
            "rows": self.rows,
            "valid_rows": self.rows - len(self.problem_rows),
            "invalid_rows": len(self.problem_rows),
            "issue_count": len(self.issues),
            "schema_errors": list(self.schema_errors),
        }


def _unique_metadata_name(base: str, existing: set[str]) -> str:
    candidate, number = base, 2
    while candidate in existing:
        candidate = f"{base}_{number}"
        number += 1
    existing.add(candidate)
    return candidate


def validate_data(
    frame: pd.DataFrame, rules: ValidationRules | dict, *, control=None
) -> QualityReport:
    """Validate positional records (header=1), including duplicate source indexes."""
    if not isinstance(frame, pd.DataFrame):
        raise DataFlowError("Validation requires a table.")
    # A frame with no columns is still useful when reporting a missing required schema.
    if len(frame.columns):
        validate_columns(frame.columns)
    rules = ValidationRules.from_dict(
        rules.to_dict() if isinstance(rules, ValidationRules) else rules
    )
    if control is not None:
        control.checkpoint()
    source = frame.reset_index(drop=True)
    issue_rows = []
    reasons = [[] for _ in range(len(frame))]
    referenced = list(
        dict.fromkeys(
            [
                *rules.required_columns,
                *rules.required_values,
                *rules.unique_columns,
                *rules.allowed_values,
                *rules.numeric_ranges,
                *rules.date_ranges,
            ]
        )
    )
    missing = [name for name in referenced if name not in source.columns]
    schema_errors = [f"Missing column: '{name}'." for name in missing]
    if schema_errors:
        for row_reasons in reasons:
            row_reasons.extend(schema_errors)

    def add(column: str, rule: str, mask: pd.Series, message: str) -> None:
        for position in source.index[mask.fillna(False)]:
            issue_rows.append(
                {"record": int(position) + 2, "column": column, "rule": rule, "message": message}
            )
            reasons[position].append(message)

    checks = [
        ("required", rules.required_values),
        ("unique", rules.unique_columns),
        ("allowed", rules.allowed_values),
        ("numeric_range", rules.numeric_ranges),
        ("date_range", rules.date_ranges),
    ]
    total = sum(len(columns) for _, columns in checks)
    completed = 0
    for rule, columns in checks:
        for column in columns:
            if control is not None:
                control.checkpoint()
            if column not in missing:
                values = source[column]
                absent = empty_mask(values)
                if rule == "required":
                    add(column, rule, absent, f"Column '{column}' requires a nonempty value.")
                elif rule == "unique":
                    add(
                        column,
                        rule,
                        ~absent & values.duplicated(keep=False),
                        f"Column '{column}' must contain unique values.",
                    )
                elif rule == "allowed":
                    add(
                        column,
                        rule,
                        ~absent & ~values.isin(rules.allowed_values[column]),
                        f"Column '{column}' contains a value outside the allowed set.",
                    )
                else:
                    bounds = (
                        rules.numeric_ranges if rule == "numeric_range" else rules.date_ranges
                    )[column]
                    invalid = pd.Series(False, index=source.index)
                    for checked, position in enumerate(source.index[~absent]):
                        if checked % 1000 == 0 and control is not None:
                            control.checkpoint()
                        value = values.iloc[position]
                        try:
                            if rule == "numeric_range":
                                if isinstance(value, bool):
                                    raise ValueError("Boolean is not numeric")
                                converted = Decimal(str(value))
                                if not converted.is_finite():
                                    raise ValueError("Nonfinite number")
                                limits = {key: Decimal(str(bound)) for key, bound in bounds.items()}
                            else:
                                if not isinstance(value, (str, date, datetime, pd.Timestamp)):
                                    raise ValueError("Not a date")
                                converted = (
                                    pd.Timestamp(value)
                                    if not isinstance(value, str)
                                    else _date_bound(value)
                                )
                                if pd.isna(converted):
                                    raise ValueError("Not a date")
                                limits = {key: _date_bound(bound) for key, bound in bounds.items()}
                            invalid.iloc[position] = any(
                                converted < bound if key == "min" else converted > bound
                                for key, bound in limits.items()
                            )
                        except (ValueError, TypeError, ArithmeticError):
                            invalid.iloc[position] = True
                    add(
                        column,
                        rule,
                        invalid,
                        f"Column '{column}' fails its {'numeric' if rule == 'numeric_range' else 'date'} range check.",
                    )
            completed += 1
            if control is not None:
                control.report("validation", completed, total)
    if control is not None:
        control.checkpoint()
    invalid_positions = [position for position, row_reasons in enumerate(reasons) if row_reasons]
    problem_rows = frame.iloc[invalid_positions].copy(deep=True)
    names = set(frame.columns)
    record_column = _unique_metadata_name("_source_record", names)
    reasons_column = _unique_metadata_name("_validation_reasons", names)
    problem_rows[record_column] = [position + 2 for position in invalid_positions]
    problem_rows[reasons_column] = ["; ".join(reasons[position]) for position in invalid_positions]
    issues = pd.DataFrame(issue_rows, columns=["record", "column", "rule", "message"])
    return QualityReport(
        len(frame), issues, problem_rows, schema_errors, record_column, reasons_column
    )
