"""Typer commands: argument handling and reporting over the shared core engine."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from dataflow.core.configuration import PipelineConfig
from dataflow.core.errors import DataFlowError
from dataflow.core.importing import ImportOptions
from dataflow.core.io import list_sheets, read_table, write_table
from dataflow.core.processor import (
    ProcessingResult,
    batch_process,
    merge_files,
    process_file,
)
from dataflow.core.quality import ValidationRules, validate_data
from dataflow.core.validation import empty_mask

app = typer.Typer(
    name="dataflow",
    help="DataFlow Studio — safe, repeatable Excel and CSV workflows.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)
logger = logging.getLogger("dataflow.cli")
T = TypeVar("T")


class Collision(StrEnum):
    error = "error"
    unique = "unique"


class MergeMode(StrEnum):
    union = "union"
    strict = "strict"
    intersection = "intersection"


class OutputFormat(StrEnum):
    csv = "csv"
    xlsx = "xlsx"


Input = Annotated[Path, typer.Argument(help="Input .csv or .xlsx file.")]
Inputs = Annotated[list[Path], typer.Argument(help="Input .csv or .xlsx files.")]
Output = Annotated[
    Path, typer.Option("--output", "-o", help="Output path; extension selects CSV or XLSX.")
]
OptionalOutput = Annotated[
    Path | None,
    typer.Option("--output", "-o", help="Output path. Default: a unique INPUT_processed file."),
]
Config = Annotated[Path, typer.Option("--config", "-c", help="JSON pipeline configuration file.")]
ImportConfig = Annotated[
    Path | None,
    typer.Option("--import-config", help="JSON import schema, formats and safety limits."),
]
Sheet = Annotated[
    str,
    typer.Option(
        "--sheet", help="Worksheet name or zero-based index. Use name:2025 for a numeric name."
    ),
]
Encoding = Annotated[str, typer.Option("--encoding", help="CSV input/output encoding.")]
Delimiter = Annotated[str, typer.Option("--delimiter", help="CSV separator. Use \\t for a tab.")]
CollisionOption = Annotated[
    Collision,
    typer.Option("--collision", help="Existing output policy; originals are always protected."),
]
OptionalCollision = Annotated[
    Collision | None,
    typer.Option(
        "--collision", help="Default: unique for automatic output, error for an explicit path."
    ),
]


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Log operation metadata to stderr.")
    ] = False,
) -> None:
    """Configure metadata-only logging without importing or starting the GUI."""
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("dataflow").setLevel(level)


def _run(operation: Callable[[], T]) -> T:
    """Map safe core errors to concise CLI failures without leaking cell values."""
    try:
        return operation()
    except DataFlowError as error:
        typer.echo(f"Error: {error}", err=True)
    except OSError as error:
        typer.echo(
            f"Error: File access failed ({type(error).__name__}). Check paths and permissions.",
            err=True,
        )
    except Exception as error:
        logger.error("Command failed (%s)", type(error).__name__)
        typer.echo(
            f"Error: Processing failed ({type(error).__name__}). Check the input and configuration.",
            err=True,
        )
    raise typer.Exit(code=1)


def _io_options(
    sheet: str, encoding: str, delimiter: str, import_config: Path | None = None
) -> dict:
    if sheet.startswith("name:"):
        selected_sheet: str | int = sheet[5:]
    else:
        selected_sheet = int(sheet) if sheet.isdecimal() else sheet
    options = {
        "sheet": selected_sheet,
        "encoding": encoding,
        "delimiter": "\t" if delimiter == "\\t" else delimiter,
    }
    if import_config is not None:
        options["import_options"] = ImportOptions.from_json(import_config)
    return options


def _emit(report: dict) -> None:
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


def _export(
    result: ProcessingResult,
    output: Path,
    *,
    encoding: str,
    delimiter: str,
    collision: str,
) -> dict:
    path = write_table(
        result.processed,
        output,
        encoding=encoding,
        delimiter=delimiter,
        collision=collision,
        source_paths=result.source_paths,
    )
    report = {**result.summary(), "output": str(path)}
    logger.info(
        "Exported %s rows from %s files", report["processed_rows"], report["files_processed"]
    )
    return report


def _process_and_export(
    source: Path,
    config: PipelineConfig,
    output: Path | None,
    collision: Collision | None,
    options: dict,
) -> dict:
    result = process_file(source, config, **options)
    target = (
        output
        if output is not None
        else source.with_name(f"{source.stem}_processed{source.suffix}")
    )
    policy = (
        collision.value if collision is not None else ("error" if output is not None else "unique")
    )
    return _export(
        result,
        target,
        encoding=options["encoding"],
        delimiter=options["delimiter"],
        collision=policy,
    )


def _fill_values(items: list[str] | None) -> dict:
    values = {}
    for item in items or []:
        column, separator, raw = item.partition("=")
        if not separator or not column.strip():
            raise typer.BadParameter("Use COLUMN=VALUE for each --fill-missing option.")
        if column in values:
            raise typer.BadParameter("Each --fill-missing column may be specified only once.")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        if isinstance(value, (dict, list)) or value is None:
            raise typer.BadParameter(
                "--fill-missing values must be non-null JSON scalars or plain text."
            )
        values[column] = value
    return values


@app.command()
def clean(
    input_file: Input,
    output: OptionalOutput = None,
    trim_whitespace: Annotated[
        bool, typer.Option("--trim-whitespace", help="Trim leading and trailing spaces.")
    ] = False,
    drop_empty_rows: Annotated[
        bool, typer.Option("--drop-empty-rows", help="Remove completely empty rows.")
    ] = False,
    normalize_columns: Annotated[
        bool, typer.Option("--normalize-columns", help="Normalize column names.")
    ] = False,
    drop_duplicates: Annotated[
        bool, typer.Option("--drop-duplicates", help="Remove repeated rows.")
    ] = False,
    deduplicate_by: Annotated[
        list[str] | None,
        typer.Option(
            "--deduplicate-by", help="Repeat for duplicate key columns; requires --drop-duplicates."
        ),
    ] = None,
    fill_missing: Annotated[
        list[str] | None,
        typer.Option(
            "--fill-missing", help="Repeat COLUMN=VALUE. Values may be JSON scalars or plain text."
        ),
    ] = None,
    drop_column: Annotated[
        list[str] | None, typer.Option("--drop-column", help="Repeat for columns to remove.")
    ] = None,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    collision: OptionalCollision = None,
    import_config: ImportConfig = None,
) -> None:
    """Clean a table using explicitly selected operations. No cleaning is enabled by default."""
    if deduplicate_by and not drop_duplicates:
        raise typer.BadParameter("--deduplicate-by requires --drop-duplicates.")
    fills = _fill_values(fill_missing)
    if not any(
        (trim_whitespace, drop_empty_rows, normalize_columns, drop_duplicates, fills, drop_column)
    ):
        raise typer.BadParameter(
            "Select at least one cleaning operation, for example --trim-whitespace or --drop-duplicates."
        )
    settings = {
        "trim_whitespace": trim_whitespace,
        "drop_empty_rows": drop_empty_rows,
        "normalize_columns": normalize_columns,
        "drop_duplicates": drop_duplicates,
        "deduplicate_by": deduplicate_by,
        "fill_missing": fills,
        "drop_columns": drop_column or [],
    }
    report = _run(
        lambda: _process_and_export(
            input_file,
            PipelineConfig.from_dict(settings),
            output,
            collision,
            _io_options(sheet, encoding, delimiter, import_config),
        )
    )
    _emit(report)


@app.command()
def process(
    input_file: Input,
    config: Config,
    output: OptionalOutput = None,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    collision: OptionalCollision = None,
    import_config: ImportConfig = None,
) -> None:
    """Execute a validated JSON pipeline and export its result."""
    report = _run(
        lambda: _process_and_export(
            input_file,
            PipelineConfig.from_json(config),
            output,
            collision,
            _io_options(sheet, encoding, delimiter, import_config),
        )
    )
    _emit(report)


@app.command()
def convert(
    input_file: Input,
    output: Output,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    collision: CollisionOption = Collision.error,
    import_config: ImportConfig = None,
) -> None:
    """Convert between CSV and XLSX. The output extension selects the format."""
    report = _run(
        lambda: _process_and_export(
            input_file,
            PipelineConfig.from_dict({}),
            output,
            collision,
            _io_options(sheet, encoding, delimiter, import_config),
        )
    )
    _emit(report)


@app.command()
def merge(
    input_files: Inputs,
    output: Output,
    mode: Annotated[
        MergeMode, typer.Option("--mode", help="Column alignment strategy.")
    ] = MergeMode.union,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    collision: CollisionOption = Collision.error,
    import_config: ImportConfig = None,
) -> None:
    """Append rows from multiple tables using union, strict, or intersection columns."""
    options = _run(lambda: _io_options(sheet, encoding, delimiter, import_config))
    report = _run(
        lambda: _export(
            merge_files(input_files, mode=mode.value, **options),
            output,
            encoding=encoding,
            delimiter=options["delimiter"],
            collision=collision.value,
        )
    )
    _emit(report)


@app.command()
def batch(
    input_files: Inputs,
    config: Config,
    output_dir: Annotated[
        Path, typer.Option("--output-dir", help="Directory for processed files.")
    ],
    output_format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format for every result.")
    ] = OutputFormat.csv,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    collision: CollisionOption = Collision.unique,
    import_config: ImportConfig = None,
) -> None:
    """Process files independently. Exit 3 means some files succeeded and some failed."""
    result = _run(
        lambda: batch_process(
            input_files,
            PipelineConfig.from_json(config),
            output_dir,
            output_format=output_format.value,
            collision=collision.value,
            **_io_options(sheet, encoding, delimiter, import_config),
        )
    )
    _emit({**result.summary(), "successes": result.successes, "errors": result.errors})
    if result.errors:
        raise typer.Exit(code=3 if result.successes else 1)


@app.command(name="inspect")
def inspect_file(
    input_file: Input,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    import_config: ImportConfig = None,
) -> None:
    """Report table metadata and missing counts without printing cell contents."""

    def inspect_metadata() -> dict:
        options = _io_options(sheet, encoding, delimiter, import_config)
        frame = read_table(input_file, **options)
        report = {
            "input": str(input_file),
            "rows": len(frame),
            "columns": list(frame.columns),
            "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
            "missing_values": {
                str(column): int(empty_mask(frame[column]).sum()) for column in frame.columns
            },
        }
        if input_file.suffix.lower() == ".xlsx":
            report["sheets"] = list_sheets(input_file, import_options=options.get("import_options"))
        return report

    _emit(_run(inspect_metadata))


@app.command()
def validate(
    input_file: Input,
    rules: Annotated[Path, typer.Option("--rules", help="JSON source validation rules.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional rejected source records CSV or XLSX."),
    ] = None,
    import_config: ImportConfig = None,
    sheet: Sheet = "0",
    encoding: Encoding = "utf-8-sig",
    delimiter: Delimiter = ",",
    collision: CollisionOption = Collision.error,
) -> None:
    """Check source data without changing it. Exit 4 means validation found issues."""

    def check_source() -> dict:
        selected_rules = ValidationRules.from_json(rules)
        options = _io_options(sheet, encoding, delimiter, import_config)
        frame = read_table(input_file, **options)
        quality = validate_data(frame, selected_rules)
        report = quality.summary()
        if output is not None:
            path = write_table(
                quality.problem_rows,
                output,
                encoding=encoding,
                delimiter=options["delimiter"],
                collision=collision.value,
                source_paths=[input_file],
            )
            report["output"] = str(path)
        return report

    report = _run(check_source)
    _emit(report)
    if report["invalid_rows"] or report["schema_errors"]:
        raise typer.Exit(code=4)


if __name__ == "__main__":
    app()
