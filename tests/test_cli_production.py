"""Production workflow CLI acceptance checks using actual CSV/XLSX files."""

import importlib.util
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from dataflow.cli import app

runner = CliRunner()


def json_file(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("command", ["inspect", "clean", "process", "convert", "merge", "batch"])
def test_all_reading_commands_apply_explicit_import_config(tmp_path, command):
    source = tmp_path / "input.csv"
    source.write_text("id,name\n001, A \n002, B \n", encoding="utf-8")
    schema = json_file(tmp_path, "import.json", {"column_types": {"id": "string"}})
    config = json_file(tmp_path, "pipeline.json", {})
    output = tmp_path / "output.csv"
    arguments = [command, str(source), "--import-config", str(schema)]
    if command == "merge":
        second = tmp_path / "second.csv"
        second.write_text("id,name\n003, C \n", encoding="utf-8")
        arguments.insert(2, str(second))
    if command == "clean":
        arguments += ["--trim-whitespace"]
    if command in {"process", "batch"}:
        arguments += ["--config", str(config)]
    if command == "batch":
        arguments += ["--output-dir", str(tmp_path / "batch")]
    elif command != "inspect":
        arguments += ["--output", str(output)]
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    if command == "inspect":
        assert report["dtypes"]["id"] == "string"
    else:
        target = next((tmp_path / "batch").glob("*.csv")) if command == "batch" else output
        expected_ids = ["001", "002", "003"] if command == "merge" else ["001", "002"]
        assert pd.read_csv(target, dtype=str)["id"].tolist() == expected_ids


@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
def test_validate_exports_exact_rejected_source_records_and_returns_four(tmp_path, suffix):
    source = tmp_path / "input.csv"
    source.write_text("id,value\n001,5\n002,99\n003,7\n", encoding="utf-8")
    original = source.read_bytes()
    schema = json_file(tmp_path, "import.json", {"column_types": {"id": "string"}})
    rules = json_file(tmp_path, "rules.json", {"numeric_ranges": {"value": {"max": 10}}})
    output = tmp_path / f"rejected.{suffix}"
    result = runner.invoke(
        app,
        [
            "validate",
            str(source),
            "--rules",
            str(rules),
            "--import-config",
            str(schema),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 4, result.output
    report = json.loads(result.output)
    assert report["rows"] == 3 and report["invalid_rows"] == 1
    assert Path(report["output"]) == output
    frame = pd.read_csv(output, dtype=str) if suffix == "csv" else pd.read_excel(output, dtype=str)
    assert frame["id"].tolist() == ["002"]
    assert "99" not in result.output
    assert source.read_bytes() == original


def test_validate_without_output_is_read_only_and_reports_schema_errors(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id\n", encoding="utf-8")
    rules = json_file(tmp_path, "rules.json", {"required_columns": ["missing"]})
    before = set(tmp_path.iterdir())
    result = runner.invoke(app, ["validate", str(source), "--rules", str(rules)])
    assert result.exit_code == 4, result.output
    report = json.loads(result.output)
    assert report["schema_errors"] and report["rows"] == 0
    assert set(tmp_path.iterdir()) == before


def test_validate_valid_data_and_source_collision(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id\n1\n", encoding="utf-8")
    rules = json_file(tmp_path, "rules.json", {"required_values": ["id"]})
    arguments = ["validate", str(source), "--rules", str(rules)]
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["invalid_rows"] == 0
    before = source.read_bytes()
    collision = runner.invoke(app, arguments + ["--output", str(source), "--collision", "unique"])
    assert collision.exit_code == 1
    assert source.read_bytes() == before


@pytest.mark.parametrize("bad_file", ["schema", "rules"])
def test_validate_invalid_json_is_sanitized_and_returns_one(tmp_path, bad_file):
    source = tmp_path / "input.csv"
    source.write_text("id\nprivate-cell\n", encoding="utf-8")
    schema = json_file(tmp_path, "import.json", {})
    rules = json_file(tmp_path, "rules.json", {})
    (schema if bad_file == "schema" else rules).write_text('{"private-secret":', encoding="utf-8")
    result = runner.invoke(
        app, ["validate", str(source), "--rules", str(rules), "--import-config", str(schema)]
    )
    assert result.exit_code == 1, result.output
    assert "private-secret" not in result.output and "private-cell" not in result.output


def test_inspect_uses_authorized_import_limits_for_sheet_discovery(tmp_path, monkeypatch):
    from dataflow.core.io import list_sheets as real_list_sheets

    source = tmp_path / "input.xlsx"
    pd.DataFrame({"id": ["001"]}).to_excel(source, index=False)
    schema = json_file(
        tmp_path, "import.json", {"column_types": {"id": "string"}, "max_file_mb": 75}
    )
    authorized_limits = []

    def discover(path, *, import_options=None):
        authorized_limits.append(import_options.max_file_mb if import_options is not None else None)
        return real_list_sheets(path, import_options=import_options)

    monkeypatch.setattr("dataflow.cli.list_sheets", discover)
    result = runner.invoke(app, ["inspect", str(source), "--import-config", str(schema)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["dtypes"]["id"] == "string"
    assert authorized_limits == [75]


def test_legacy_smoke_restores_user_environment_even_when_checks_fail(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "gui_smoke.py"
    spec = importlib.util.spec_from_file_location("legacy_gui_smoke", script)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    old_workspace = str(tmp_path / "user-workspace")
    old_appdata = str(tmp_path / "user-appdata")
    monkeypatch.setenv("DATAFLOW_WORKSPACE_DIR", old_workspace)
    monkeypatch.setenv("LOCALAPPDATA", old_appdata)
    isolated_paths = []

    def fail_without_opening_gui():
        isolated_paths.extend(
            Path(os.environ[key]) for key in ("DATAFLOW_WORKSPACE_DIR", "LOCALAPPDATA")
        )
        assert os.environ["DATAFLOW_WORKSPACE_DIR"] != old_workspace
        assert os.environ["LOCALAPPDATA"] != old_appdata
        for path in isolated_paths:
            path.mkdir(parents=True)
            (path / "synthetic-state.txt").write_text("test", encoding="utf-8")
        raise RuntimeError("synthetic check failure")

    monkeypatch.setattr(smoke, "_run_smoke", fail_without_opening_gui)
    with pytest.raises(RuntimeError, match="synthetic check failure"):
        smoke.main()
    assert os.environ["DATAFLOW_WORKSPACE_DIR"] == old_workspace
    assert os.environ["LOCALAPPDATA"] == old_appdata
    assert isolated_paths and all(not path.exists() for path in isolated_paths)
    assert not Path(old_workspace).exists() and not Path(old_appdata).exists()
