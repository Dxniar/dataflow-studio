"""Shared orchestration for in-memory, file, merge, and partial-success batch workflows."""

import copy
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pandas.api.types import infer_dtype, is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from . import cleaning, transformations
from .configuration import PipelineConfig
from .errors import DataFlowError
from .io import read_table, validate_csv_options, write_table
from .jobs import JobCancelled, JobControl
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
    pending: list[str] = field(default_factory=list)
    cancelled: bool = False

    def summary(self) -> dict:
        summary = {
            "processed": len(self.successes),
            "failed": len(self.errors),
            "files": len(self.successes) + len(self.errors) + len(self.pending),
        }
        if self.pending or self.cancelled:
            summary.update(pending=len(self.pending), cancelled=self.cancelled)
        return summary

    def to_dict(self) -> dict:
        return copy.deepcopy(
            {
                "successes": self.successes,
                "errors": self.errors,
                "pending": self.pending,
                "cancelled": self.cancelled,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict) -> "BatchResult":
        message = "Invalid batch checkpoint. Choose a valid saved batch run."
        if not isinstance(payload, dict) or not {"successes", "errors"} <= payload.keys():
            raise DataFlowError(message)
        if set(payload) - {"successes", "errors", "pending", "cancelled"}:
            raise DataFlowError(message)
        successes, errors = payload["successes"], payload["errors"]
        pending, cancelled = payload.get("pending", []), payload.get("cancelled", False)
        if not all(isinstance(items, list) for items in (successes, errors, pending)):
            raise DataFlowError(message)
        if type(cancelled) is not bool or any(
            not isinstance(path, str) or not path for path in pending
        ):
            raise DataFlowError(message)
        for item in successes:
            if (
                not isinstance(item, dict)
                or set(item) != {"input", "output", "summary"}
                or not all(
                    isinstance(item[name], str) and item[name] for name in ("input", "output")
                )
                or not isinstance(item["summary"], dict)
            ):
                raise DataFlowError(message)
        for item in errors:
            if (
                not isinstance(item, dict)
                or set(item) != {"input", "error"}
                or not all(
                    isinstance(item[name], str) and item[name] for name in ("input", "error")
                )
            ):
                raise DataFlowError(message)
        try:
            json.dumps(payload, allow_nan=False)
            identities = [_path_identity(item["input"]) for item in successes + errors]
            identities.extend(_path_identity(path) for path in pending)
            if len(identities) != len(set(identities)):
                raise DataFlowError(message)
        except (TypeError, ValueError, OSError, RuntimeError):
            raise DataFlowError(message) from None
        return cls(copy.deepcopy(successes), copy.deepcopy(errors), list(pending), cancelled)


def _path_identity(path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def _checkpoint(control) -> None:
    if control is not None:
        control.checkpoint()


def _report(control, stage, completed, total, message="") -> None:
    if control is not None:
        control.report(stage, completed, total, message)


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


def process_frame(
    frame: pd.DataFrame, config: PipelineConfig, *, control: JobControl | None = None
) -> ProcessingResult:
    started = time.perf_counter()
    _checkpoint(control)
    if not isinstance(frame, pd.DataFrame):
        raise DataFlowError("Input must be a pandas DataFrame.")
    config = _config(config)
    _validate_references(frame, config)
    original = frame.copy(deep=True)
    processed = frame.copy(deep=True)
    operations = []
    duplicates_removed = 0
    total = sum(
        bool(getattr(config, name))
        for name in (
            "trim_whitespace",
            "drop_empty_rows",
            "normalize_columns",
            "standardize_values",
            "fill_missing",
            "convert_types",
            "drop_duplicates",
            "rename_columns",
            "drop_columns",
            "select_columns",
            "reorder_columns",
            "filters",
            "sort_by",
        )
    )
    _report(control, "transform", 0, total)

    def apply(operation, description):
        _checkpoint(control)
        result = operation()
        _checkpoint(control)
        operations.append(description)
        _report(control, "transform", len(operations), total, description)
        _checkpoint(control)
        return result

    try:
        if config.trim_whitespace:
            processed = apply(lambda: cleaning.trim_whitespace(processed), "Trim whitespace")
        if config.drop_empty_rows:
            processed = apply(lambda: cleaning.drop_empty_rows(processed), "Remove empty rows")
        if config.normalize_columns:
            processed = apply(
                lambda: processed.set_axis(normalized_columns(processed.columns), axis=1),
                "Normalize column names",
            )
        if config.standardize_values:
            processed = apply(
                lambda: cleaning.standardize_values(processed, config.standardize_values),
                "Standardize values",
            )
        if config.fill_missing:
            processed = apply(
                lambda: cleaning.fill_missing(processed, config.fill_missing), "Fill missing values"
            )
        if config.convert_types:
            processed = apply(
                lambda: transformations.convert_types(processed, config.convert_types),
                "Convert types",
            )
        if config.drop_duplicates:
            count = len(processed)
            processed = apply(
                lambda: processed.drop_duplicates(subset=config.deduplicate_by).copy(),
                "Remove duplicates",
            )
            duplicates_removed = count - len(processed)
        if config.rename_columns:
            processed = apply(
                lambda: processed.rename(columns=config.rename_columns), "Rename columns"
            )
        if config.drop_columns:
            processed = apply(lambda: processed.drop(columns=config.drop_columns), "Drop columns")
        if config.select_columns:
            processed = apply(lambda: processed[config.select_columns].copy(), "Select columns")
        if config.reorder_columns:
            processed = apply(lambda: processed[config.reorder_columns].copy(), "Reorder columns")
        if config.filters:
            processed = apply(
                lambda: transformations.filter_rows(processed, config.filters), "Filter rows"
            )
        if config.sort_by:
            processed = apply(
                lambda: processed.sort_values(
                    config.sort_by,
                    ascending=config.sort_ascending,
                    kind="stable",
                    na_position="last",
                ),
                "Sort rows",
            )
    except DataFlowError:
        raise
    except Exception:
        raise DataFlowError(
            "Processing failed because the selected operation is incompatible with the column data."
        ) from None
    # Retain the input index when no transformations are requested; it is never exported.
    if operations:
        _checkpoint(control)
        processed = processed.reset_index(drop=True)
    _checkpoint(control)
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
    control: JobControl | None = None,
    import_options=None,
) -> ProcessingResult:
    started = time.perf_counter()
    config = _config(config)
    _checkpoint(control)
    _report(control, "read", 0, 1)
    result = process_frame(
        read_table(
            path,
            sheet=sheet,
            encoding=encoding,
            delimiter=delimiter,
            import_options=import_options,
            control=control,
        ),
        config,
        control=control,
    )
    _report(control, "read", 1, 1)
    _checkpoint(control)
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
    control: JobControl | None = None,
    import_options=None,
) -> ProcessingResult:
    started = time.perf_counter()
    paths = list(paths)
    if len(paths) < 2:
        raise DataFlowError("Merge requires at least two input files.")
    if mode not in {"union", "strict", "intersection"}:
        raise DataFlowError("Merge mode must be union, strict, or intersection.")
    frames = []
    _report(control, "read", 0, len(paths))
    for path in paths:
        _checkpoint(control)
        frames.append(
            read_table(
                path,
                sheet=sheet,
                encoding=encoding,
                delimiter=delimiter,
                import_options=import_options,
                control=control,
            )
        )
        _checkpoint(control)
        _report(control, "read", len(frames), len(paths))
    _checkpoint(control)
    _report(control, "merge", 0, 1)
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
        _checkpoint(control)
        families = {_type_family(frame[column]) for frame in frames if column in frame.columns}
        families.discard(None)
        if len(families) > 1:
            raise DataFlowError(
                f"Cannot merge incompatible types in column '{column}'. Standardize its type first."
            )
    _checkpoint(control)
    original = pd.concat(frames, ignore_index=True, sort=False)
    _checkpoint(control)
    processed = pd.concat([frame.reindex(columns=columns) for frame in frames], ignore_index=True)
    _checkpoint(control)
    _report(control, "merge", 1, 1)
    _checkpoint(control)
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
    control: JobControl | None = None,
    import_options=None,
    checkpoint_callback: Callable[[BatchResult], None] | None = None,
    resume_from: BatchResult | dict | None = None,
) -> BatchResult:
    config = _config(config)
    if output_format not in {"csv", "xlsx"}:
        raise DataFlowError("Batch output format must be csv or xlsx.")
    if collision not in {"error", "unique"}:
        raise DataFlowError("Collision policy must be 'error' or 'unique'.")
    validate_csv_options(encoding, delimiter)
    paths = list(paths)
    if not paths and resume_from is None:
        raise DataFlowError("Batch processing requires at least one file.")
    if resume_from is None:
        try:
            unique = {}
            for path in paths:
                unique.setdefault(_path_identity(path), str(path))
        except (OSError, TypeError, RuntimeError):
            raise DataFlowError("Invalid or inaccessible batch input path.") from None
        result = BatchResult(pending=list(unique.values()))
    else:
        result = BatchResult.from_dict(
            resume_from.to_dict() if isinstance(resume_from, BatchResult) else resume_from
        )
        result.pending = [item["input"] for item in result.errors] + result.pending
        result.errors = []
        result.cancelled = False
    protected_sources = paths + [item["input"] for item in result.successes] + result.pending
    try:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
    except (OSError, TypeError, RuntimeError):
        raise DataFlowError("Cannot create or access the batch output directory.") from None
    total = len(result.successes) + len(result.pending)

    def snapshot():
        if checkpoint_callback is not None:
            checkpoint_callback(BatchResult.from_dict(result.to_dict()))

    _report(control, "batch", len(result.successes), total)
    for path in list(result.pending):
        try:
            _checkpoint(control)
            processed = process_file(
                path,
                config,
                sheet=sheet,
                encoding=encoding,
                delimiter=delimiter,
                import_options=import_options,
                control=control,
            )
            _checkpoint(control)
            output = write_table(
                processed.processed,
                directory / f"{Path(path).stem}_processed.{output_format}",
                encoding=encoding,
                delimiter=delimiter,
                collision=collision,
                source_paths=protected_sources,
                control=control,
            )
            result.successes.append(
                {"input": str(path), "output": str(output), "summary": processed.summary()}
            )
        except JobCancelled:
            result.cancelled = True
            snapshot()
            break
        except DataFlowError as error:
            result.errors.append({"input": str(path), "error": str(error)})
            logger.warning("Batch item failed: error=%s", type(error).__name__)
        except Exception:
            result.errors.append({"input": str(path), "error": "Unexpected file processing error."})
            logger.warning("Batch item failed unexpectedly")
        result.pending.remove(path)
        snapshot()
        _report(control, "batch", len(result.successes) + len(result.errors), total)
    return result
