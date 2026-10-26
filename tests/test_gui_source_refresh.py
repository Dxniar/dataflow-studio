"""Replacing source data invalidates validation results before export is possible."""

from types import SimpleNamespace

import pandas as pd

from dataflow.core.jobs import JobControl
from dataflow.core.quality import validate_data
from dataflow.gui.app import DataFlowApp, LoadedFile


def _headless_app(current):
    report = validate_data(current.frame, {"allowed_values": {"id": [2]}})
    assert report.problem_rows["id"].tolist() == [1]
    app = SimpleNamespace(
        current_file=current,
        quality_report=report,
        result=None,
        import_options={},
        runner=SimpleNamespace(control=JobControl()),
        page_name="Data Validation",
        _import_options=lambda: {},
        _refresh_file_bar=lambda: None,
        show_page=lambda _: None,
        set_status=lambda *args, **kwargs: None,
    )

    def submit(name, work, finish):
        finish(work())
        return True

    app._submit = submit
    return app


def test_reloading_source_clears_rejected_rows_from_previous_contents(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes(b"id\n2\n")
    current = LoadedFile(source, pd.DataFrame({"id": [1]}), [])
    app = _headless_app(current)

    assert DataFlowApp.reload_current(app)

    assert current.frame["id"].tolist() == [2]
    assert app.quality_report is None


def test_switching_worksheet_clears_rejected_rows_from_previous_sheet(tmp_path):
    source = tmp_path / "source.xlsx"
    with pd.ExcelWriter(source) as workbook:
        pd.DataFrame({"id": [1]}).to_excel(workbook, sheet_name="Original", index=False)
        pd.DataFrame({"id": [2]}).to_excel(workbook, sheet_name="Updated", index=False)
    current = LoadedFile(source, pd.DataFrame({"id": [1]}), ["Original", "Updated"], "Original")
    app = _headless_app(current)

    DataFlowApp._select_sheet(app, "Updated")

    assert current.frame["id"].tolist() == [2]
    assert current.sheet == "Updated"
    assert app.quality_report is None
