"""Shared orchestration for in-memory, file, merge, and partial-success batch workflows."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pandas.api.types import infer_dtype, is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from . import cleaning, transformations
from .configuration import PipelineConfig
from .errors import DataFlowError
from .io import read_table, validate_csv_options, write_table
from .validation import missing_count, normalized_columns, require_columns, validate_columns

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    original: pd.DataFrame
    processed: pd.DataFrame
    operations: list[str]
    duplicates_removed: int
    elapsed_seconds: float
    files_processed: int = 1
    source_paths: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "original_rows": len(self.original),
            "processed_rows": len(self.processed),
            "original_columns": len(self.original.columns),
            "processed_columns": len(self.processed.columns),
            "duplicates_removed": self.duplicates_removed,
            "missing_before": missing_count(self.original),
            "missing_after": missing_count(self.processed),
            "files_processed": self.files_processed,
            "operations": list(self.operations),
            "elapsed_seconds": round(self.elapsed_seconds, 6),
        }


@dataclass
class BatchResult:
    successes: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "processed": len(self.successes),
            "failed": len(self.errors),
            "files": len(self.successes) + len(self.errors),
        }


def _config(config: PipelineConfig) -> PipelineConfig:
    if not isinstance(config, PipelineConfig):
        raise DataFlowError("A validated PipelineConfig is required.")
    # Revalidate mutable nested options at the boundary and isolate them from callers.
    return PipelineConfig.from_dict(config.to_dict())


def _validate_references(frame: pd.DataFrame, config: PipelineConfig) -> None:
    """Check every column reference against the schema at that operation's point."""
    columns = validate_columns(frame.columns)
    if config.normalize_columns:
        columns = normalized_columns(columns)
    schema = pd.DataFrame(columns=columns)
    for operation in ("standardize_values", "fill_missing", "convert_types"):
        require_columns(schema, getattr(config, operation), operation)
    if config.drop_duplicates and config.deduplicate_by:
        require_columns(schema, config.deduplicate_by, "deduplicate_by")
    require_columns(schema, config.rename_columns, "rename_columns")
    schema.columns = validate_columns([config.rename_columns.get(name, name) for name in columns])
    for operation in ("drop_columns", "select_columns", "reorder_columns"):
        names = getattr(config, operation)
        if not names:
            continue
        require_columns(schema, names, operation)
        if operation == "drop_columns":
            schema = schema.drop(columns=names)
            validate_columns(schema.columns)
        elif operation == "select_columns":
            schema = schema[names]
        else:
            if set(names) != set(schema.columns):
                raise DataFlowError(
                    "reorder_columns must contain every remaining column exactly once."
                )
            schema = schema[names]
    require_columns(schema, [condition["column"] for condition in config.filters], "filters")
    require_columns(schema, config.sort_by, "sort_by")


def process_frame(frame: pd.DataFrame, config: PipelineConfig) -> ProcessingResult:
    started = time.perf_counter()
    if not isinstance(frame, pd.DataFrame):
        raise DataFlowError("Input must be a pandas DataFrame.")
    config = _config(config)
    _validate_references(frame, config)
    original = frame.copy(deep=True)
    processed = frame.copy(deep=True)
    operations = []
    duplicates_removed = 0
    try:
        if config.trim_whitespace:
            processed = cleaning.trim_whitespace(processed)
            operations.append("Trim whitespace")
        if config.drop_empty_rows:
            processed = cleaning.drop_empty_rows(processed)
            operations.append("Remove empty rows")
        if config.normalize_columns:
            processed.columns = normalized_columns(processed.columns)
            operations.append("Normalize column names")
        if config.standardize_values:
            processed = cleaning.standardize_values(processed, config.standardize_values)
            operations.append("Standardize values")
        if config.fill_missing:
            processed = cleaning.fill_missing(processed, config.fill_missing)
            operations.append("Fill missing values")
        if config.convert_types:
            processed = transformations.convert_types(processed, config.convert_types)
            operations.append("Convert types")
        if config.drop_duplicates:
            count = len(processed)
            processed = processed.drop_duplicates(subset=config.deduplicate_by).copy()
            duplicates_removed = count - len(processed)
            operations.append("Remove duplicates")
        if config.rename_columns:
            processed = processed.rename(columns=config.rename_columns)
            operations.append("Rename columns")
        if config.drop_columns:
            processed = processed.drop(columns=config.drop_columns)
            operations.append("Drop columns")
        if config.select_columns:
            processed = processed[config.select_columns].copy()
            operations.append("Select columns")
        if config.reorder_columns:
            processed = processed[config.reorder_columns].copy()
            operations.append("Reorder columns")
        if config.filters:
            processed = transformations.filter_rows(processed, config.filters)
            operations.append("Filter rows")
        if config.sort_by:
            processed = processed.sort_values(
                config.sort_by, ascending=config.sort_ascending, kind="stable", na_position="last"
            )
            operations.append("Sort rows")
    except DataFlowError:
        raise
    except Exception:
        raise DataFlowError(
            "Processing failed because the selected operation is incompatible with the column data."
        ) from None
    # Retain the input index when no transformations are requested; it is never exported.
    if operations:
        processed = processed.reset_index(drop=True)
    elapsed = time.perf_counter() - started
    logger.info(
        "Processed table: before=%d after=%d operations=%d elapsed=%.3fs",
        len(original),
        len(processed),
        len(operations),
        elapsed,
    )
    return ProcessingResult(original, processed, operations, duplicates_removed, elapsed)


def process_file(
    path: str | Path,
    config: PipelineConfig,
    *,
    sheet: int | str = 0,
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
) -> ProcessingResult:
    started = time.perf_counter()
    config = _config(config)
    result = process_frame(
        read_table(path, sheet=sheet, encoding=encoding, delimiter=delimiter), config
    )
    result.elapsed_seconds = time.perf_counter() - started
    result.source_paths = [str(Path(path).expanduser().resolve())]
    return result


def _type_family(series: pd.Series) -> str | None:
    present = series.dropna()
    if present.empty:
        return None
    if is_bool_dtype(present):
        return "boolean"
    if is_numeric_dtype(present):
        return "numeric"
    if is_datetime64_any_dtype(present):
        return "datetime"
    return infer_dtype(present, skipna=True)


def merge_files(
    paths,
    *,
    mode: str = "union",
    sheet: int | str = 0,
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
) -> ProcessingResult:
    started = time.perf_counter()
    paths = list(paths)
    if len(paths) < 2:
        raise DataFlowError("Merge requires at least two input files.")
    if mode not in {"union", "strict", "intersection"}:
        raise DataFlowError("Merge mode must be union, strict, or intersection.")
    frames = [
        read_table(path, sheet=sheet, encoding=encoding, delimiter=delimiter) for path in paths
    ]
    columns = list(frames[0].columns)
    if mode == "strict":
        if any(set(frame.columns) != set(columns) for frame in frames[1:]):
            raise DataFlowError("Strict merge requires matching column names in every file.")
    elif mode == "intersection":
        columns = [name for name in columns if all(name in frame.columns for frame in frames)]
        if not columns:
            raise DataFlowError("The selected files have no common columns.")
    else:
        columns = list(dict.fromkeys(name for frame in frames for name in frame.columns))
    for column in columns:
        families = {_type_family(frame[column]) for frame in frames if column in frame.columns}
        families.discard(None)
        if len(families) > 1:
            raise DataFlowError(
                f"Cannot merge incompatible types in column '{column}'. Standardize its type first."
            )
    original = pd.concat(frames, ignore_index=True, sort=False)
    processed = pd.concat([frame.reindex(columns=columns) for frame in frames], ignore_index=True)
    elapsed = time.perf_counter() - started
    logger.info(
        "Merged tables: files=%d rows=%d columns=%d elapsed=%.3fs",
        len(paths),
        len(processed),
        len(columns),
        elapsed,
    )
    return ProcessingResult(
        original.copy(deep=True),
        processed.copy(deep=True),
        [f"Merge files ({mode})"],
        0,
        elapsed,
        len(paths),
        [str(Path(path).expanduser().resolve()) for path in paths],
    )


def batch_process(
    paths,
    config: PipelineConfig,
    output_dir: str | Path,
    *,
    output_format: str = "csv",
    sheet: int | str = 0,
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    collision: str = "unique",
) -> BatchResult:
    config = _config(config)
    if output_format not in {"csv", "xlsx"}:
        raise DataFlowError("Batch output format must be csv or xlsx.")
    if collision not in {"error", "unique"}:
        raise DataFlowError("Collision policy must be 'error' or 'unique'.")
    validate_csv_options(encoding, delimiter)
    paths = list(paths)
    if not paths:
        raise DataFlowError("Batch processing requires at least one file.")
    try:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
    except (OSError, TypeError, RuntimeError):
        raise DataFlowError("Cannot create or access the batch output directory.") from None
    result = BatchResult()
    for path in paths:
        try:
            processed = process_file(
                path, config, sheet=sheet, encoding=encoding, delimiter=delimiter
            )
            output = write_table(
                processed.processed,
                directory / f"{Path(path).stem}_processed.{output_format}",
                encoding=encoding,
                delimiter=delimiter,
                collision=collision,
                source_paths=paths,
            )
            result.successes.append(
                {"input": str(path), "output": str(output), "summary": processed.summary()}
            )
        except DataFlowError as error:
            result.errors.append({"input": str(path), "error": str(error)})
            logger.warning("Batch item failed: error=%s", type(error).__name__)
        except Exception:
            result.errors.append({"input": str(path), "error": "Unexpected file processing error."})
            logger.warning("Batch item failed unexpectedly")
    return result
