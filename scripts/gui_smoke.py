"""Exercise the real Tk window; run manually on a desktop, never in headless CI."""

import hashlib
import json
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


def main():
    paths = [
        ROOT / "examples/input/customers_dirty.csv",
        ROOT / "examples/input/customers_dirty.xlsx",
    ]
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    app = DataFlowApp()
    callback_errors = []
    app.report_callback_exception = lambda kind, value, trace: callback_errors.append(str(value))
    report = {"desktop": True, "pages": [], "checks": []}
    try:
        app.update()
        for page in app.PAGE_NAMES:
            app.show_page(page)
            app.update()
            report["pages"].append(page)
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
        assert tables and tables[0].table.winfo_height() >= 100, "Dashboard preview is clipped"
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
        assert all(item.table.winfo_height() >= 100 for item in previews(app.page)), (
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
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    (output / "gui-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
