"""Exercise the real Tk window; run manually on a desktop, never in headless CI."""

import gc
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from dataflow.core.io import read_table
from dataflow.gui.app import DataFlowApp
from dataflow.gui.components import DataPreview

ROOT = Path(__file__).resolve().parents[1]


def wait_for(app, *, allow_error=False):
    deadline = time.monotonic() + 30
    # Let the queue deliver completion even when a tiny job finishes immediately.
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(0.02)
    app.update()
    assert not app.busy, "GUI operation timed out"
    if not allow_error:
        assert app.last_error is None, app.last_error


def _run_smoke():
    paths = [
        ROOT / "examples/input/customers_dirty.csv",
        ROOT / "examples/input/customers_dirty.xlsx",
    ]
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    app = DataFlowApp()
    callback_errors = []
    finalizer_errors = []
    original_unraisable_hook = sys.unraisablehook
    sys.unraisablehook = lambda error: finalizer_errors.append(str(error.exc_value))
    app.report_callback_exception = lambda kind, value, trace: callback_errors.append(str(value))
    report = {"desktop": True, "pages": [], "checks": []}
    try:
        app.update()
        for page in app.PAGE_NAMES:
            app.show_page(page)
            app.update()
            report["pages"].append(page)
        app._submit("Widget lifecycle check", gc.collect, lambda value: None)
        wait_for(app)
        assert not finalizer_errors, finalizer_errors
        assert app.load_paths(paths)
        wait_for(app)
        assert len(app.files) == 2 and len(app.current_frame) == 153
        app.show_page("Dashboard")
        app.update()

        def previews(widget):
            found = [widget] if isinstance(widget, DataPreview) else []
            for child in widget.winfo_children():
                found.extend(previews(child))
            return found

        tables = previews(app.page)
        assert tables and tables[0].table.winfo_height() >= 150, "Dashboard preview is clipped"
        report["checks"].append("CSV and XLSX import and preview")
        app.select_file(1)
        app._select_sheet("About")
        wait_for(app)
        assert list(app.current_frame.columns) == ["notice"]
        app._select_sheet("Customers")
        wait_for(app)
        report["checks"].append("Excel worksheet switching")
        app.select_file(0)
        config = json.loads((ROOT / "examples/demo_config.json").read_text(encoding="utf-8"))
        app.apply_config(config)
        assert app.run_processing()
        assert not app.run_processing(), "A duplicate run was accepted while busy"
        wait_for(app)
        assert len(app.result.processed) == 132 and app.result.duplicates_removed == 18
        # At the smallest default window, keep at least three complete data rows.
        assert all(item.table.winfo_height() >= 140 for item in previews(app.page)), (
            "Comparison tables are clipped"
        )
        report["summary"] = app.result.summary()
        report["checks"].append("Shared workflow and before/after metrics")
        with TemporaryDirectory(prefix="dataflow-gui-") as temp:
            output = Path(temp)
            assert app.export_result(output / "result.xlsx")
            wait_for(app)
            assert len(read_table(app.last_export)) == 132
            report["checks"].append("XLSX export verified by reading actual output")
            assert app.export_result(paths[0])
            wait_for(app, allow_error=True)
            assert app.last_error and not app.busy
            report["checks"].append("Source overwrite rejected and controls recovered")
            app.output_format_var.set("xlsx")
            assert app.run_conversion(output / "converted.xlsx")
            wait_for(app)
            assert len(read_table(app.last_export)) == 153
            report["checks"].append("Conversion preserves original table")
            assert app.run_batch(output / "batch")
            wait_for(app)
            assert len(app.last_batch.successes) == 2 and not app.last_batch.errors
            report["checks"].append("Batch exports two files with real summaries")
            assert app.run_merge()
            wait_for(app)
            assert len(app.result.processed) == 306
            report["checks"].append("Merge appends matching schemas")
        app.change_theme("Graphite")
        app.update()
        app.change_theme("Midnight")
        app.update()
        report["checks"].append("Theme switch and all navigation pages")
        assert not callback_errors, callback_errors
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == hashes
        report["checks"].append("Original source hashes unchanged")
        report["passed"] = True
    finally:
        app.destroy()
        sys.unraisablehook = original_unraisable_hook
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    (output / "gui-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    """Run native checks with disposable state instead of actual user settings."""
    keys = ("DATAFLOW_WORKSPACE_DIR", "LOCALAPPDATA")
    original = {key: os.environ.get(key) for key in keys}
    logger = logging.getLogger("dataflow")
    previous_level, previous_propagate = logger.level, logger.propagate
    with TemporaryDirectory(prefix="dataflow-gui-state-") as temporary:
        directory = Path(temporary).resolve()
        try:
            os.environ["DATAFLOW_WORKSPACE_DIR"] = str(directory / "workspace")
            os.environ["LOCALAPPDATA"] = str(directory / "appdata")
            _run_smoke()
        finally:
            # Windows cannot remove the temporary log folder while its handler
            # owns an open file. Close only handlers created inside this folder.
            for handler in logger.handlers[:]:
                filename = getattr(handler, "baseFilename", None)
                if filename and Path(filename).resolve().is_relative_to(directory):
                    logger.removeHandler(handler)
                    handler.close()
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    main()
