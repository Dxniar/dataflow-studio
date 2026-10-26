"""Typed import preserves source text and rejects unsafe or malformed schemas."""

import json
import struct
from zipfile import ZIP_DEFLATED, ZipFile

import openpyxl
import pandas as pd
import pytest

from dataflow.core.errors import DataFlowError
from dataflow.core.io import read_table


def options(**kwargs):
    from dataflow.core.importing import ImportOptions

    return ImportOptions(**kwargs)


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_explicit_string_preserves_leading_zero_blank_zero_and_literal_na(tmp_path, extension):
    path = tmp_path / f"ids.{extension}"
    if extension == "csv":
        path.write_text("id,note\n0012,NA\n0,NULL\n,\n", encoding="utf-8")
    else:
        workbook = openpyxl.Workbook()
        for row in [["id", "note"], ["0012", "NA"], ["0", "NULL"], [None, None]]:
            workbook.active.append(row)
        # An actual empty interior record, not a trailing blank discarded by Excel.
        workbook.active.append(["0013", "end"])
        workbook.save(path)
        workbook.close()
    frame = read_table(path, import_options=options(column_types={"id": "string"}))
    assert frame.loc[0, "id"] == "0012"
    assert frame.loc[1, "id"] == "0"
    assert pd.isna(frame.loc[2, "id"])
    assert frame.loc[0, "note"] == "NA"
    assert frame.loc[1, "note"] == "NULL"


def test_european_numbers_explicit_dates_nullable_integer_and_boolean(tmp_path):
    path = tmp_path / "typed.csv"
    path.write_text(
        "amount;day;count;active\n1.234,50;31/12/2026;2;true\n0,00;01/01/2027;;false\n",
        encoding="utf-8",
    )
    frame = read_table(
        path,
        delimiter=";",
        import_options=options(
            column_types={
                "amount": "float",
                "day": "datetime",
                "count": "integer",
                "active": "boolean",
            },
            date_formats={"day": "%d/%m/%Y"},
            decimal=",",
            thousands=".",
        ),
    )
    assert frame["amount"].tolist() == [1234.5, 0.0]
    assert frame["day"].tolist() == [pd.Timestamp("2026-12-31"), pd.Timestamp("2027-01-01")]
    assert frame.loc[0, "count"] == 2 and pd.isna(frame.loc[1, "count"])
    assert frame["active"].tolist() == [True, False]


@pytest.mark.parametrize(
    "kind,value",
    [
        ("integer", "2.5"),
        ("integer", "9007199254740993.1"),
        ("float", "private-cell"),
        ("float", "inf"),
        ("datetime", "private-cell"),
        ("datetime", "NaT"),
        ("boolean", "private-cell"),
    ],
)
def test_invalid_conversions_fail_without_cell_values(tmp_path, kind, value):
    path = tmp_path / "invalid.csv"
    path.write_text(f"value\n{value}\n", encoding="utf-8")
    with pytest.raises(DataFlowError) as error:
        read_table(path, import_options=options(column_types={"value": kind}))
    assert value not in str(error.value)
    assert "convert" in str(error.value).lower()


def test_unknown_schema_columns_fail_even_on_empty_input(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("id\n", encoding="utf-8")
    with pytest.raises(DataFlowError, match="column"):
        read_table(path, import_options=options(column_types={"absent": "string"}))


@pytest.mark.parametrize(
    "payload",
    [
        {"extra": True},
        {"column_types": {"id": "python"}},
        {"column_types": []},
        {"column_types": {"": "string"}},
        {"date_formats": {"id": "%d"}},
        {"decimal": ",", "thousands": ","},
        {"decimal": ".."},
        {"thousands": ""},
        {"max_rows": True},
        {"max_rows": 0},
        {"max_file_mb": -1},
        {"max_table_mb": 1.5},
    ],
)
def test_import_options_reject_invalid_configuration(payload):
    from dataflow.core.importing import ImportOptions

    with pytest.raises(DataFlowError):
        ImportOptions.from_dict(payload)


def test_import_options_roundtrip_is_detached_and_duplicate_json_is_rejected(tmp_path):
    from dataflow.core.importing import ImportOptions

    schema = {"id": "string"}
    configured = options(column_types=schema)
    schema["id"] = "float"
    payload = configured.to_dict()
    assert payload["column_types"] == {"id": "string"}
    path = tmp_path / "import.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert ImportOptions.from_json(path).to_dict() == payload
    payload["column_types"]["id"] = "integer"
    assert configured.column_types == {"id": "string"}
    path.write_text('{"decimal":".","decimal":","}', encoding="utf-8")
    with pytest.raises(DataFlowError):
        ImportOptions.from_json(path)


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
@pytest.mark.parametrize("limits", [{"max_rows": 1}, {"max_cells": 3}])
def test_import_rejects_row_and_cell_limits_before_returning(tmp_path, extension, limits):
    path = tmp_path / f"large.{extension}"
    frame = pd.DataFrame({"id": [1, 2], "value": [3, 4]})
    if extension == "csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_excel(path, index=False)
    with pytest.raises(DataFlowError, match="limit exceeded"):
        read_table(path, import_options=options(**limits))


def test_file_and_table_memory_guards(tmp_path):
    path = tmp_path / "large.csv"
    path.write_text(
        "value\n" + "x" * 1024 + "\n" * 2 + ("y" * 1024 + "\n") * 1100, encoding="utf-8"
    )
    with pytest.raises(DataFlowError, match="limit exceeded"):
        read_table(path, import_options=options(max_file_mb=1))
    with pytest.raises(DataFlowError, match="limit exceeded"):
        read_table(path, import_options=options(max_table_mb=1))


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_header_reader_does_not_load_table(tmp_path, extension):
    from dataflow.core.io import read_columns

    path = tmp_path / f"header.{extension}"
    if extension == "csv":
        path.write_text('id,name\n1,"unterminated', encoding="utf-8")
    else:
        pd.DataFrame({"id": ["001"], "name": ["A"]}).to_excel(
            path, sheet_name="Chosen", index=False
        )
    assert read_columns(path, sheet="Chosen" if extension == "xlsx" else 0) == ["id", "name"]


def test_excel_locale_numeric_parsing_keeps_explicit_strings_and_native_dates(tmp_path):
    path = tmp_path / "locale.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["id", "amount", "native_amount", "day"])
    sheet.append(["001.002", "1.234,50", 1234.5, pd.Timestamp("2026-10-26").to_pydatetime()])
    workbook.save(path)
    workbook.close()
    frame = read_table(
        path,
        import_options=options(
            column_types={
                "id": "string",
                "amount": "float",
                "native_amount": "float",
                "day": "datetime",
            },
            decimal=",",
            thousands=".",
            date_formats={"day": "%d/%m/%Y"},
        ),
    )
    assert frame.loc[0, "id"] == "001.002"
    assert frame.loc[0, "amount"] == 1234.5
    assert frame.loc[0, "native_amount"] == 1234.5
    assert frame.loc[0, "day"] == pd.Timestamp("2026-10-26")


def test_integer_larger_than_float_precision_retains_exact_value_with_missing_cells(tmp_path):
    path = tmp_path / "integer.csv"
    path.write_text("id\n9007199254740993\n\n", encoding="utf-8")
    frame = read_table(path, import_options=options(column_types={"id": "integer"}))
    assert frame.loc[0, "id"] == 9007199254740993
    assert pd.isna(frame.loc[1, "id"])


@pytest.mark.parametrize("reader", ["read_columns", "list_sheets"])
def test_header_and_sheet_discovery_reject_oversized_files_before_opening(tmp_path, reader):
    from dataflow.core import io

    path = tmp_path / "oversized.xlsx"
    with path.open("wb") as stream:
        stream.seek(50 * 1024 * 1024)
        stream.write(b"x")
    with pytest.raises(DataFlowError, match="limit exceeded"):
        getattr(io, reader)(path)


@pytest.mark.parametrize("reader", ["read_table", "read_columns", "list_sheets"])
def test_workbook_expansion_guard_runs_before_openpyxl_reads_shared_data(tmp_path, reader):
    from dataflow.core import io

    path = tmp_path / "expanded.xlsx"
    pd.DataFrame({"id": [1]}).to_excel(path, index=False)
    with ZipFile(path, "a") as archive:
        archive.writestr("unused-large-resource", b"small")
    data = bytearray(path.read_bytes())
    # An archive can claim enormous expanded resources even when the file itself is small.
    position = data.rfind(b"PK\x01\x02")
    struct.pack_into("<I", data, position + 24, 300 * 1024 * 1024)
    path.write_bytes(data)
    with pytest.raises(DataFlowError, match="limit exceeded"):
        getattr(io, reader)(path)


@pytest.mark.parametrize("stage", ["parse", "read_complete"])
def test_source_changed_during_import_is_rejected_instead_of_bypassing_preflight(tmp_path, stage):
    from dataflow.core.jobs import JobControl

    path = tmp_path / "changing.csv"
    path.write_text("id\n1\n", encoding="utf-8")

    def replace_source(event):
        if (stage == "parse" and event.stage == "parse") or (
            stage == "read_complete" and event.stage == "read" and event.completed > 0
        ):
            path.write_text("id\n" + ("x" * 1000 + "\n") * 1200, encoding="utf-8")

    with pytest.raises(DataFlowError, match="changed"):
        read_table(path, import_options=options(max_file_mb=1), control=JobControl(replace_source))


@pytest.mark.parametrize("reader", ["read_columns", "list_sheets"])
def test_workbook_discovery_uses_configured_file_limit_and_allows_raising_it(tmp_path, reader):
    from dataflow.core import io

    path = tmp_path / "discovery.xlsx"
    pd.DataFrame({"id": [1]}).to_excel(path, index=False)
    with ZipFile(path, "a") as archive:
        archive.writestr("unused-padding", b"x" * (1024 * 1024 + 100))
    expected = ["id"] if reader == "read_columns" else ["Sheet1"]
    assert getattr(io, reader)(path) == expected
    with pytest.raises(DataFlowError, match="file size limit exceeded"):
        getattr(io, reader)(path, import_options={"max_file_mb": 1})
    assert getattr(io, reader)(path, import_options=options(max_file_mb=2)) == expected


@pytest.mark.parametrize("reader", ["read_columns", "list_sheets"])
def test_workbook_discovery_uses_configured_expansion_limit(tmp_path, reader):
    from dataflow.core import io

    path = tmp_path / "expanded-discovery.xlsx"
    pd.DataFrame({"id": [1]}).to_excel(path, index=False)
    with ZipFile(path, "a", compression=ZIP_DEFLATED) as archive:
        with archive.open("unused-padding", "w") as stream:
            block = b"x" * (1024 * 1024)
            for _ in range(5):
                stream.write(block)
    expected = ["id"] if reader == "read_columns" else ["Sheet1"]
    with pytest.raises(DataFlowError, match="Expanded workbook size limit exceeded"):
        getattr(io, reader)(path, import_options=options(max_table_mb=1))
    assert getattr(io, reader)(path, import_options={"max_table_mb": 2}) == expected


def test_csv_header_discovery_uses_configured_file_limit(tmp_path):
    from dataflow.core.io import read_columns

    path = tmp_path / "header-discovery.csv"
    path.write_text("id\n" + "x" * (1024 * 1024 + 100), encoding="utf-8")
    with pytest.raises(DataFlowError, match="file size limit exceeded"):
        read_columns(path, import_options={"max_file_mb": 1})
    assert read_columns(path, import_options=options(max_file_mb=2)) == ["id"]


@pytest.mark.parametrize("reader", ["read_columns", "list_sheets"])
def test_discovery_rejects_invalid_import_configuration(tmp_path, reader):
    from dataflow.core import io

    path = tmp_path / "invalid-options.xlsx"
    pd.DataFrame({"id": [1]}).to_excel(path, index=False)
    with pytest.raises(DataFlowError):
        getattr(io, reader)(path, import_options={"max_file_mb": True})
