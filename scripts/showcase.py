"""Open the real app with synthetic files ready for a manual demonstration."""

import argparse
import json
import time
from pathlib import Path

from dataflow.gui.app import DataFlowApp

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Play a real 60-second workflow, waiting for artifacts/start-showcase.",
    )
    args = parser.parse_args()
    app = DataFlowApp()
    app.state("zoomed")
    app.output_dir_var.set(str(ROOT / "examples" / "output"))
    app.after(
        300,
        lambda: app.load_paths(
            [
                ROOT / "examples/input/customers_dirty.csv",
                ROOT / "examples/input/customers_dirty.xlsx",
            ]
        ),
    )
    if args.auto:
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        started = None
        completed = set()
        config = json.loads((ROOT / "examples/demo_config.json").read_text(encoding="utf-8"))

        def step():
            nonlocal started
            if not app.files or app.busy:
                app.after(100, step)
                return
            if started is None:
                if not (artifacts / "start-showcase").exists():
                    app.after(100, step)
                    return
                started = time.monotonic()
                (artifacts / "showcase-started.json").write_text(json.dumps({"epoch": time.time()}))
            elapsed = time.monotonic() - started
            phases = [
                (7, "input", lambda: app.show_page("Convert Files")),
                (
                    17,
                    "operations",
                    lambda: (app.show_page("Data Cleaning"), app.apply_config(config)),
                ),
                (27, "processing", app.run_processing),
                (40, "export", lambda: app.export_result(ROOT / "examples/output/gui_demo.xlsx")),
                (44, "batch", lambda: app.run_batch(ROOT / "examples/output/gui_batch")),
                (52, "results", lambda: app.show_page("History & Logs")),
            ]
            for at, name, action in phases:
                if elapsed >= at and name not in completed:
                    completed.add(name)
                    action()
                    (artifacts / "showcase-phase.json").write_text(
                        json.dumps({"phase": name, "elapsed": elapsed, "error": app.last_error})
                    )
                    break
            if elapsed < 61:
                app.after(100, step)
            else:
                (artifacts / "showcase-done.json").write_text(
                    json.dumps(
                        {
                            "passed": app.last_error is None
                            and app.result is not None
                            and app.last_batch is not None
                            and len(app.last_batch.successes) == 2,
                            "summary": app.result.summary() if app.result else None,
                            "batch": app.last_batch.summary() if app.last_batch else None,
                            "export": str(app.last_export),
                        },
                        indent=2,
                    )
                )

        app.after(700, step)
    app.mainloop()


if __name__ == "__main__":
    main()
