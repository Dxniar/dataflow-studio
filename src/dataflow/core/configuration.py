"""Strict JSON configuration. Operations are opt-in and never execute expressions."""

import copy
import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .errors import DataFlowError

TYPE_NAMES = {"string", "integer", "float", "datetime", "boolean"}
FILTER_OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "greater_than",
    "less_than",
    "is_empty",
    "is_not_empty",
}


def _scalar(value: Any) -> bool:
    return (
        value is None
        or type(value) in (str, bool, int)
        or (type(value) is float and math.isfinite(value))
    )


def _names(value: Any, option: str, *, allow_empty: bool = True) -> None:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise DataFlowError(f"'{option}' must be a list of nonempty column names.")
    if len(value) != len(set(value)) or (not allow_empty and not value):
        raise DataFlowError(f"'{option}' must contain unique column names and cannot be empty.")


def _mapping(value: Any, option: str) -> None:
    if not isinstance(value, dict) or any(not isinstance(k, str) or not k.strip() for k in value):
        raise DataFlowError(f"'{option}' must be an object with nonempty column names.")


def _validate(options: dict) -> None:
    for name in (
        "trim_whitespace",
        "drop_empty_rows",
        "normalize_columns",
        "drop_duplicates",
        "sort_ascending",
    ):
        if type(options[name]) is not bool:
            raise DataFlowError(f"'{name}' must be true or false.")
    if options["deduplicate_by"] is not None:
        _names(options["deduplicate_by"], "deduplicate_by", allow_empty=False)
    for name in ("drop_columns", "select_columns", "reorder_columns", "sort_by"):
        _names(options[name], name)
    for name in ("fill_missing", "standardize_values", "rename_columns", "convert_types"):
        _mapping(options[name], name)
    if any(not _scalar(value) for value in options["fill_missing"].values()):
        raise DataFlowError("'fill_missing' values must be finite JSON scalars.")
    for mapping in options["standardize_values"].values():
        if not isinstance(mapping, dict) or any(
            not isinstance(key, str) or not _scalar(value) for key, value in mapping.items()
        ):
            raise DataFlowError("'standardize_values' requires text-to-scalar mappings.")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in options["rename_columns"].values()
    ):
        raise DataFlowError("'rename_columns' requires nonempty replacement names.")
    if any(
        not isinstance(value, str) or value not in TYPE_NAMES
        for value in options["convert_types"].values()
    ):
        raise DataFlowError("'convert_types' supports string, integer, float, datetime, boolean.")
    filters = options["filters"]
    if not isinstance(filters, list):
        raise DataFlowError("'filters' must be a list of conditions.")
    for condition in filters:
        if not isinstance(condition, dict) or set(condition) - {"column", "operator", "value"}:
            raise DataFlowError("Each filter accepts only column, operator, and value.")
        if not isinstance(condition.get("column"), str) or not condition["column"].strip():
            raise DataFlowError("Each filter needs a nonempty column name.")
        operator = condition.get("operator")
        if not isinstance(operator, str) or operator not in FILTER_OPERATORS:
            raise DataFlowError("Unsupported filter operator.")
        if operator not in {"is_empty", "is_not_empty"} and "value" not in condition:
            raise DataFlowError("This filter requires a value.")
        if not _scalar(condition.get("value")):
            raise DataFlowError("Filter values must be finite JSON scalars.")
        if operator == "contains" and not isinstance(condition["value"], str):
            raise DataFlowError("A contains filter requires text.")
        if operator in {"greater_than", "less_than"} and type(condition["value"]) not in (
            int,
            float,
        ):
            raise DataFlowError("Numeric comparison filters require a numeric value.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            raise DataFlowError("Configuration contains a duplicate JSON key.")
        output[key] = value
    return output


@dataclass
class PipelineConfig:
    """Ordered pipeline options; see docs/API_CONTRACT.md for operation order."""

    trim_whitespace: bool = False
    drop_empty_rows: bool = False
    normalize_columns: bool = False
    drop_duplicates: bool = False
    deduplicate_by: list[str] | None = None
    fill_missing: dict[str, Any] = field(default_factory=dict)
    standardize_values: dict[str, dict[str, Any]] = field(default_factory=dict)
    rename_columns: dict[str, str] = field(default_factory=dict)
    drop_columns: list[str] = field(default_factory=list)
    select_columns: list[str] = field(default_factory=list)
    reorder_columns: list[str] = field(default_factory=list)
    convert_types: dict[str, str] = field(default_factory=dict)
    filters: list[dict[str, Any]] = field(default_factory=list)
    sort_by: list[str] = field(default_factory=list)
    sort_ascending: bool = True

    def __post_init__(self) -> None:
        options = {item.name: getattr(self, item.name) for item in fields(self)}
        _validate(options)
        for key, value in options.items():
            setattr(self, key, copy.deepcopy(value))

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        if not isinstance(data, dict):
            raise DataFlowError("Pipeline configuration must be a JSON object.")
        allowed = {item.name for item in fields(cls)}
        if set(data) - allowed:
            raise DataFlowError("Unknown pipeline option. Check the configuration reference.")
        return cls(**copy.deepcopy(data))

    @classmethod
    def from_json(cls, path: str | Path) -> "PipelineConfig":
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
            data = json.loads(content, object_pairs_hook=_unique_object)
        except DataFlowError:
            raise
        except (OSError, UnicodeError, ValueError):
            raise DataFlowError("Cannot read configuration. Use a valid UTF-8 JSON file.") from None
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return asdict(self)
