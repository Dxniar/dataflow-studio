"""CLI acceptance tests exercise real files and the shared processing engine."""

import importlib.util
import json

import pandas as pd
import pytest
from rich.text import Text
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_app():
    assert importlib.util.find_spec("dataflow.cli") is not None, "CLI is not implemented"
    from dataflow.cli import app

    return app


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "клиенты.csv"
    path.write_text(
        "id,name,city\n1, Айдана ,Алматы\n1, Айдана ,Алматы\n2,Émile,\n", encoding="utf-8-sig"
    )
    return path


def test_help_lists_supported_workflows(cli_app):
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0, result.output
    for command in ("clean", "process", "convert", "merge", "batch", "inspect"):
        assert command in result.output


def test_clean_requires_explicit_operations(cli_app, source):
    before = source.read_bytes()
    result = runner.invoke(cli_app, ["clean", str(source)])
    assert result.exit_code == 2
    assert "operation" in result.output.lower()
    assert source.read_bytes() == before
    assert list(source.parent.glob("*_processed*")) == []


def test_clean_trims_and_deduplicates_without_disclosing_cells(cli_app, source, tmp_path):
    output = tmp_path / "таза.xlsx"
    result = runner.invoke(
        cli_app,
        [
            "clean",
            str(source),
            "--output",
            str(output),
            "--trim-whitespace",
            "--drop-duplicates",
            "--deduplicate-by",
            "id",
        ],
    )
    assert result.exit_code == 0, result.output
    frame = pd.read_excel(output)
    assert frame["id"].tolist() == [1, 2]
    assert frame["name"].tolist() == ["Айдана", "Émile"]
    assert frame["city"].iloc[0] == "Алматы"
    assert pd.isna(frame["city"].iloc[1])
    summary = json.loads(result.output)
    assert summary["original_rows"] == 3
    assert summary["processed_rows"] == 2
    assert summary["duplicates_removed"] == 1
    assert "Айдана" not in result.output


def test_process_default_output_is_unique_and_preserves_original(cli_app, source, tmp_path):
    config = tmp_path / "pipeline.json"
    config.write_text('{"trim_whitespace": true, "drop_duplicates": true}', encoding="utf-8")
    original = source.read_bytes()
    first = runner.invoke(cli_app, ["process", str(source), "--config", str(config)])
    second = runner.invoke(cli_app, ["process", str(source), "--config", str(config)])
    assert first.exit_code == second.exit_code == 0, first.output + second.output
    first_output = json.loads(first.output)["output"]
    second_output = json.loads(second.output)["output"]
    assert first_output != second_output
    assert source.read_bytes() == original
    assert len(pd.read_csv(first_output)) == len(pd.read_csv(second_output)) == 2


def test_process_matches_gui_controller(cli_app, source, tmp_path):
    from dataflow.core.io import read_table
    from dataflow.gui.controller import run_pipeline

    settings = {
        "trim_whitespace": True,
        "drop_duplicates": True,
        "sort_by": ["id"],
        "sort_ascending": False,
    }
    config = tmp_path / "pipeline.json"
    config.write_text(json.dumps(settings), encoding="utf-8")
    output = tmp_path / "parity.csv"
    result = runner.invoke(
        cli_app, ["process", str(source), "--config", str(config), "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    gui_result = run_pipeline(read_table(source), settings)
    pd.testing.assert_frame_equal(read_table(output), gui_result.processed.reset_index(drop=True))
    assert read_table(output)["id"].tolist() == [2, 1]


def test_convert_roundtrip_unicode_and_selects_sheet(cli_app, tmp_path):
    source = tmp_path / "кіріс.xlsx"
    with pd.ExcelWriter(source) as workbook:
        pd.DataFrame({"name": ["wrong"]}).to_excel(workbook, sheet_name="first", index=False)
        pd.DataFrame({"name": ["Әлібек", "Мария", "English"]}).to_excel(
            workbook, sheet_name="Клиенты", index=False
        )
    csv = tmp_path / "нәтиже.csv"
    xlsx = tmp_path / "нәтиже.xlsx"
    first = runner.invoke(
        cli_app,
        ["convert", str(source), "--sheet", "Клиенты", "--output", str(csv), "--delimiter", ";"],
    )
    second = runner.invoke(
        cli_app, ["convert", str(csv), "--output", str(xlsx), "--delimiter", ";"]
    )
    assert first.exit_code == second.exit_code == 0, first.output + second.output
    assert pd.read_excel(xlsx)["name"].tolist() == ["Әлібек", "Мария", "English"]


def test_merge_union_aligns_columns_and_reports_files(cli_app, tmp_path):
    first, second, output = [tmp_path / name for name in ("a.csv", "b.csv", "merged.csv")]
    first.write_text("id,name\n1,Alpha\n", encoding="utf-8")
    second.write_text("id,city\n2,Алматы\n", encoding="utf-8")
    result = runner.invoke(cli_app, ["merge", str(first), str(second), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert list(pd.read_csv(output).columns) == ["id", "name", "city"]
    assert json.loads(result.output)["files_processed"] == 2


def test_batch_keeps_successful_files_and_returns_partial_failure(cli_app, source, tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"trim_whitespace": true}', encoding="utf-8")
    output_dir = tmp_path / "batch"
    result = runner.invoke(
        cli_app,
        [
            "batch",
            str(source),
            str(tmp_path / "missing.csv"),
            "--config",
            str(config),
            "--output-dir",
            str(output_dir),
            "--format",
            "xlsx",
        ],
    )
    assert result.exit_code == 3, result.output
    report = json.loads(result.stdout)
    assert report["processed"] == 1
    assert report["failed"] == 1
    assert len(list(output_dir.glob("*.xlsx"))) == 1


def test_batch_returns_failure_when_no_file_succeeds(cli_app, tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"trim_whitespace": true}', encoding="utf-8")
    result = runner.invoke(
        cli_app,
        [
            "batch",
            str(tmp_path / "missing.csv"),
            "--config",
            str(config),
            "--output-dir",
            str(tmp_path / "batch"),
        ],
    )
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["failed"] == 1


def test_inspect_reports_metadata_without_values(cli_app, source):
    result = runner.invoke(cli_app, ["inspect", str(source)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["rows"] == 3
    assert report["columns"] == ["id", "name", "city"]
    assert report["missing_values"]["city"] == 1
    assert "Айдана" not in result.output


def test_explicit_output_collision_fails_without_overwriting(cli_app, source, tmp_path):
    output = tmp_path / "existing.csv"
    output.write_text("KEEP ME", encoding="utf-8")
    result = runner.invoke(
        cli_app, ["clean", str(source), "--output", str(output), "--trim-whitespace"]
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert output.read_text(encoding="utf-8") == "KEEP ME"


def test_source_overwrite_is_refused(cli_app, source):
    before = source.read_bytes()
    result = runner.invoke(
        cli_app, ["clean", str(source), "--output", str(source), "--trim-whitespace"]
    )
    assert result.exit_code == 1
    assert source.read_bytes() == before


@pytest.mark.parametrize("config", ['{"unknown": true}', "not json"])
def test_bad_config_returns_friendly_error_without_traceback(cli_app, source, tmp_path, config):
    path = tmp_path / "invalid.json"
    path.write_text(config, encoding="utf-8")
    result = runner.invoke(cli_app, ["process", str(source), "--config", str(path)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output


def test_missing_input_returns_friendly_error(cli_app, tmp_path):
    result = runner.invoke(cli_app, ["inspect", str(tmp_path / "missing.csv")])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output


def test_clean_fill_and_drop_options(cli_app, source, tmp_path):
    output = tmp_path / "filled.csv"
    result = runner.invoke(
        cli_app,
        [
            "clean",
            str(source),
            "--fill-missing",
            "city=Unknown",
            "--drop-column",
            "name",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    frame = pd.read_csv(output)
    assert list(frame.columns) == ["id", "city"]
    assert frame["city"].tolist() == ["Алматы", "Алматы", "Unknown"]


def test_invalid_fill_option_is_usage_error(cli_app, source):
    result = runner.invoke(cli_app, ["clean", str(source), "--fill-missing", "city"])
    assert result.exit_code == 2
    assert "COLUMN=VALUE" in result.output


@pytest.mark.parametrize("force_color", [False, True])
def test_deduplicate_by_requires_explicit_drop_duplicates(
    cli_app, source, monkeypatch, force_color
):
    if force_color:
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("COLUMNS", "80")
    result = runner.invoke(cli_app, ["clean", str(source), "--deduplicate-by", "id"])
    assert result.exit_code == 2
    assert "--drop-duplicates" in Text.from_ansi(result.output).plain


def test_inspect_counts_whitespace_cells_consistently_with_core(cli_app, tmp_path):
    source = tmp_path / "missing.csv"
    source.write_text('id,value\n1,"   "\n2,\n3,present\n', encoding="utf-8")
    result = runner.invoke(cli_app, ["inspect", str(source)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["missing_values"]["value"] == 2


def test_inspect_selects_numeric_worksheet_name(cli_app, tmp_path):
    source = tmp_path / "years.xlsx"
    with pd.ExcelWriter(source) as workbook:
        pd.DataFrame({"wrong": [1]}).to_excel(workbook, sheet_name="first", index=False)
        pd.DataFrame({"expected": [1, 2]}).to_excel(workbook, sheet_name="2025", index=False)
    result = runner.invoke(cli_app, ["inspect", str(source), "--sheet", "name:2025"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["columns"] == ["expected"]
    assert json.loads(result.stdout)["rows"] == 2


def test_verbose_output_is_valid_json_and_tab_delimiter_is_supported(cli_app, tmp_path):
    source = tmp_path / "tab.csv"
    source.write_text("id\tname\n1\tPrivate sample\n", encoding="utf-8")
    result = runner.invoke(cli_app, ["--verbose", "inspect", str(source), "--delimiter", "\\t"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["columns"] == ["id", "name"]
    assert "Private sample" not in result.output
