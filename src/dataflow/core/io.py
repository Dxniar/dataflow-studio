"""Local CSV/XLSX data IO with safe text exports and atomic, no-clobber publication."""

import codecs
import csv
import logging
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.cell import WriteOnlyCell

from .errors import DataFlowError
from .validation import validate_columns

logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


def _path(path: str | Path, *, must_exist: bool = False) -> Path:
    try:
        resolved = Path(path).expanduser().resolve()
        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise DataFlowError("Unsupported file type. Choose a .csv or .xlsx file.")
        if must_exist and not resolved.is_file():
            raise DataFlowError(f"Input file does not exist or is not a file: {resolved.name}.")
        return resolved
    except (OSError, TypeError, RuntimeError):
        raise DataFlowError("Invalid or inaccessible file path.") from None


def validate_csv_options(encoding: str, delimiter: str) -> None:
    if not isinstance(encoding, str):
        raise DataFlowError("CSV encoding must be a supported encoding name.")
    try:
        codecs.lookup(encoding)
    except LookupError:
        raise DataFlowError("Unknown CSV encoding. Try utf-8-sig or cp1251.") from None
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n\x00"':
        raise DataFlowError("CSV delimiter must be one character, excluding quotes and newlines.")


def _validate_csv_structure(path: Path, encoding: str, delimiter: str) -> None:
    with path.open(encoding=encoding, newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            raise DataFlowError("CSV file is empty. A header row is required.") from None
        validate_columns(header)
        for row in reader:
            if row and len(row) != len(header):
                raise DataFlowError(
                    "CSV rows have inconsistent field counts. Check its delimiter and quoting."
                )


def _sheet_name(names: list[str], sheet: int | str) -> str:
    if type(sheet) is int and 0 <= sheet < len(names):
        return names[sheet]
    if isinstance(sheet, str) and sheet in names:
        return sheet
    raise DataFlowError(
        "Excel sheet was not found. Select an existing sheet name or zero-based index."
    )


def list_sheets(path: str | Path) -> list[str]:
    source = _path(path, must_exist=True)
    if source.suffix.lower() != ".xlsx":
        raise DataFlowError("Sheet selection is only available for XLSX workbooks.")
    try:
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
        try:
            return list(workbook.sheetnames)
        finally:
            workbook.close()
    except Exception:
        # XLSX libraries can raise backend-specific XML errors containing raw data.
        raise DataFlowError(
            "Cannot read workbook. Check access and that it is a valid XLSX file."
        ) from None


def read_table(
    path: str | Path, *, sheet: int | str = 0, encoding: str = "utf-8-sig", delimiter: str = ","
) -> pd.DataFrame:
    source = _path(path, must_exist=True)
    try:
        if source.suffix.lower() == ".csv":
            validate_csv_options(encoding, delimiter)
            _validate_csv_structure(source, encoding, delimiter)
            frame = pd.read_csv(
                source,
                encoding=encoding,
                sep=delimiter,
                keep_default_na=False,
                na_values=[""],
                skip_blank_lines=False,
                on_bad_lines="error",
            )
        else:
            with pd.ExcelFile(source, engine="openpyxl") as excel:
                name = _sheet_name(excel.sheet_names, sheet)
                header_rows = list(
                    excel.book[name].iter_rows(min_row=1, max_row=1, values_only=True)
                )
                if not header_rows:
                    raise DataFlowError("Excel sheet is empty. A header row is required.")
                validate_columns(header_rows[0])
                frame = pd.read_excel(excel, sheet_name=name, keep_default_na=False, na_values=[""])
        validate_columns(frame.columns)
    except DataFlowError:
        raise
    except Exception:
        # Parsers often include complete cells/rows in their exceptions: never forward them.
        raise DataFlowError(
            f"Cannot read '{source.name}'. Check its format, encoding, delimiter, and file access."
        ) from None
    logger.info(
        "Read table: rows=%d columns=%d format=%s", len(frame), len(frame.columns), source.suffix
    )
    return frame


def _csv_text(value):
    if isinstance(value, str):
        stripped = value.lstrip(" \t\r\n\v\f\ufeff")
        if value.startswith(("\t", "\r", "\n")) or stripped.startswith(("=", "+", "-", "@")):
            return "'" + value
    return value


def _write_xlsx(frame: pd.DataFrame, temporary: Path) -> None:
    if len(frame) + 1 > 1_048_576 or len(frame.columns) > 16_384:
        raise DataFlowError("Table exceeds Excel's row or column limit. Export CSV instead.")
    workbook = openpyxl.Workbook(write_only=True)
    worksheet = workbook.create_sheet("Data")

    def cells(values):
        row = []
        for value in values:
            if pd.isna(value):
                value = None
            elif isinstance(value, pd.Timestamp):
                value = value.to_pydatetime()
            elif hasattr(value, "item"):
                value = value.item()
            cell = WriteOnlyCell(worksheet, value=value)
            if isinstance(value, str):
                if len(value) > 32_767:
                    raise DataFlowError(
                        "A text cell exceeds Excel's 32,767 character limit. Export CSV instead."
                    )
                cell.data_type = "s"
            row.append(cell)
        return row

    try:
        worksheet.append(cells(frame.columns))
        for values in frame.itertuples(index=False, name=None):
            worksheet.append(cells(values))
        workbook.save(temporary)
    finally:
        if not worksheet.closed:
            worksheet.close()
        workbook.close()


def write_table(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    collision: str = "error",
    source_paths: Iterable[str | Path] = (),
) -> Path:
    """Write completely to a sibling temp file, then atomically publish without overwrite.

    CSV formula-like strings receive an apostrophe; XLSX strings are explicitly text cells.
    Atomic publication uses a hard link on POSIX and non-replacing rename on Windows.
    """
    destination = _path(path)
    if collision not in {"error", "unique"}:
        raise DataFlowError("Collision policy must be 'error' or 'unique'.")
    validate_columns(frame.columns)
    validate_csv_options(encoding, delimiter)
    for source in source_paths:
        try:
            if Path(source).expanduser().resolve() == destination:
                raise DataFlowError(
                    "Export cannot use an original input path. Choose a different filename."
                )
        except (OSError, TypeError, RuntimeError):
            raise DataFlowError("Cannot validate the original file path.") from None
    if destination.exists() and collision == "error":
        raise DataFlowError(f"Output already exists: {destination.name}. Choose another filename.")

    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, filename = tempfile.mkstemp(
            prefix=".dataflow-", suffix=destination.suffix, dir=destination.parent
        )
        os.close(handle)
        temporary = Path(filename)
        if destination.suffix.lower() == ".csv":
            safe = frame.map(_csv_text)
            safe.columns = [_csv_text(column) for column in frame.columns]
            safe.to_csv(temporary, index=False, encoding=encoding, sep=delimiter)
        else:
            _write_xlsx(frame, temporary)
        # Windows FlushFileBuffers (used by fsync) requires a writable handle.
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        candidate = destination
        number = 1
        while True:
            try:
                if os.name == "nt":
                    # Windows rename fails if candidate exists; unlike POSIX rename, it cannot clobber.
                    os.rename(temporary, candidate)
                else:
                    os.link(temporary, candidate)
                break
            except FileExistsError:
                if collision == "error":
                    raise DataFlowError("Output already exists. Choose another filename.") from None
                candidate = destination.with_name(
                    f"{destination.stem}_{number}{destination.suffix}"
                )
                number += 1
        logger.info(
            "Exported table: rows=%d columns=%d format=%s",
            len(frame),
            len(frame.columns),
            candidate.suffix,
        )
        return candidate
    except DataFlowError:
        raise
    except Exception:
        raise DataFlowError(
            "Cannot export table. Check folder access, available space, encoding, and Excel cell limits."
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
