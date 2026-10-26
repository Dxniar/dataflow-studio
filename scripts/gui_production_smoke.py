"""Real desktop reliability checks with a hard-stop/restart boundary.

Run manually on an interactive Windows desktop, never during another UI test:
    python scripts/gui_production_smoke.py
    python scripts/gui_production_smoke.py --hold

The parent starts two Python processes using the current interpreter and source
checkout. Phase 1 exits with os._exit after a durable batch checkpoint. Phase 2
recovers that workspace. All sources, logs, exports and SQLite metadata live in
artifacts/gui-production-smoke/run-<id>; actual user application data is unused.

With --hold, verification.json is published while the final verification window
remains visible. Create .superpowers/finish-production-smoke.signal to close it.
All waits have deadlines. The test-only checkpoint wrapper pauses workers after
real SQLite persistence; it never replaces processing, cancellation or exports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "gui-production-smoke"
FINISH_SIGNAL = ROOT / ".superpowers" / "finish-production-smoke.signal"
SOURCE_ONE = (
    "id;name;amount;created_at\n"
    "00123; Alice ;1.234,50;26/10/2026\n"
    "00456;;-5,00;25/10/2026\n"
    "00123;Carol;7,00;24/10/2026\n"
    "00789;Dana;0,00;23/10/2026\n"
)
SOURCE_TWO = "id;name;amount;created_at\n00999;Bob;2.000,00;22/10/2026\n"
RULES = {
    "required_columns": ["id", "name"],
    "required_values": ["id", "name"],
    "unique_columns": ["id"],
    "numeric_ranges": {"amount": {"min": 0}},
}
WORKFLOW = {"trim_whitespace": True, "sort_by": ["amount"]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def durable_json(path, payload):
    """Flush evidence before the deliberate hard stop bypasses normal cleanup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Evidence:
    def __init__(self, phase):
        self.data = {"phase": phase, "checks": [], "desktop": True}

    def check(self, name, condition, **details):
        if not condition:
            raise AssertionError(name)
        self.data["checks"].append({"name": name, "passed": True, **details})


def pump(app, condition, *, description, timeout=40):
    """Keep Tk responsive until an observable condition; fail boundedly."""
    deadline = time.monotonic() + timeout
    while True:
        app.update()
        if app._smoke_callback_errors:
            raise AssertionError(
                f"Tk callback failed during {description}: {app._smoke_callback_errors}"
            )
        if condition():
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description}")
        time.sleep(0.01)


def idle(app, *, allow_error=False):
    pump(app, lambda: not app.busy, description="worker completion")
    if not allow_error and app.last_error is not None:
        raise AssertionError(f"GUI operation failed: {app.last_error}")


def new_app():
    # Import only inside children after environment isolation has been applied.
    from dataflow.gui.app import DataFlowApp

    app = DataFlowApp()
    app._smoke_callback_errors = []
    app.report_callback_exception = lambda kind, value, trace: app._smoke_callback_errors.append(
        str(value)
    )
    app.update()
    return app


class CheckpointGate:
    """Pause once after the first real successful per-file checkpoint."""

    def __init__(self, app):
        self.app = app
        self.reached = threading.Event()
        self.release = threading.Event()
        self.original = app.workspace.update_job
        self.snapshot = None
        self.job_id = None

    def install(self):
        def update(job_id, status, *, checkpoint=None, error=None):
            result = self.original(job_id, status, checkpoint=checkpoint, error=error)
            if (
                not self.reached.is_set()
                and status == "running"
                and checkpoint
                and len(checkpoint.get("successes", [])) == 1
                and len(checkpoint.get("pending", [])) == 1
            ):
                stored = self.app.workspace.get_job(job_id)
                if not stored or stored["checkpoint"] != checkpoint:
                    raise AssertionError("Checkpoint gate did not observe durable SQLite state")
                self.snapshot = checkpoint
                self.job_id = job_id
                self.reached.set()
                if not self.release.wait(timeout=45):
                    raise TimeoutError("Checkpoint gate was not released")
            return result

        self.app.workspace.update_job = update
        return self

    def restore(self):
        self.release.set()
        self.app.workspace.update_job = self.original


def csv_outputs(directory):
    return sorted(Path(directory).glob("*.csv"))


def check_batch_outputs(evidence, app, directory, first_path, first_hash, label):
    evidence.check(
        label + ": two successes, no errors or pending inputs",
        len(app.last_batch.successes) == 2
        and not app.last_batch.errors
        and not app.last_batch.pending
        and not app.last_batch.cancelled,
    )
    evidence.check(
        label + ": exactly two outputs; first result preserved",
        len(csv_outputs(directory)) == 2 and digest(first_path) == first_hash,
        first_output=str(first_path),
        first_sha256=first_hash,
    )


def phase_one(run_dir):
    import pandas as pd

    from dataflow.gui.import_dialog import ImportDialog

    evidence = Evidence("before-hard-stop")
    inputs = run_dir / "inputs"
    inputs.mkdir()
    first, second = inputs / "customers.csv", inputs / "additional.csv"
    first.write_text(SOURCE_ONE, encoding="utf-8-sig")
    second.write_text(SOURCE_TWO, encoding="utf-8-sig")
    source_hashes = {str(path): digest(path) for path in (first, second)}
    app = new_app()
    gate = None
    hard_stop = False
    try:
        dialog = ImportDialog(app, paths=[first, second], path=first)
        dialog.delimiter.set(";")
        dialog.decimal.set(",")
        dialog.thousands.set(".")
        dialog.refresh_columns()
        evidence.check(
            "Import dialog reads semicolon headers",
            dialog.headers_valid and set(dialog.types) == {"id", "name", "amount", "created_at"},
        )
        for column, kind in (
            ("id", "Text"),
            ("name", "Text"),
            ("amount", "Decimal"),
            ("created_at", "Date"),
        ):
            dialog.types[column].set(kind)
        dialog.formats["created_at"].delete(0, "end")
        dialog.formats["created_at"].insert(0, "%d/%m/%Y")
        dialog.apply()
        idle(app)
        evidence.check(
            "Actual dialog imports both files with leading-zero text IDs",
            len(app.files) == 2
            and app.current_frame["id"].tolist() == ["00123", "00456", "00123", "00789"],
        )
        evidence.check(
            "German numbers and explicit dates import correctly",
            app.current_frame["amount"].tolist() == [1234.5, -5.0, 7.0, 0.0]
            and app.current_frame["created_at"].dt.strftime("%Y-%m-%d").tolist()
            == ["2026-10-26", "2026-10-25", "2026-10-24", "2026-10-23"],
        )
        source_frame = app.current_frame.copy(deep=True)
        app.apply_validation_rules(RULES)
        evidence.check("Validation job accepted", app.run_validation())
        idle(app)
        quality = app.quality_report
        evidence.check(
            "Quality rules reject exactly source records 2, 3 and 4",
            quality.summary()["valid_rows"] == 1
            and quality.summary()["invalid_rows"] == 3
            and not quality.schema_errors
            and quality.problem_rows["id"].tolist() == ["00123", "00456", "00123"]
            and quality.problem_rows[quality.source_record_column].tolist() == [2, 3, 4],
        )
        rejected = run_dir / "rejected.xlsx"
        evidence.check("Rejected XLSX export accepted", app.export_problems(rejected))
        idle(app)
        rejected_frame = pd.read_excel(rejected, dtype={"id": str})
        evidence.check(
            "Actual rejected workbook contains exactly the rejected original records",
            rejected_frame["id"].tolist() == ["00123", "00456", "00123"]
            and rejected_frame[quality.source_record_column].tolist() == [2, 3, 4]
            and rejected_frame["amount"].tolist() == [1234.5, -5.0, 7.0],
        )
        pd.testing.assert_frame_equal(app.current_frame, source_frame)
        app.apply_config(WORKFLOW)
        evidence.check("Processing job accepted", app.run_processing())
        idle(app)
        processed = run_dir / "processed.xlsx"
        evidence.check("Processed XLSX export accepted", app.export_result(processed))
        idle(app)
        processed_frame = pd.read_excel(processed, dtype={"id": str})
        evidence.check(
            "Processed export is sorted, trimmed and retains text IDs",
            processed_frame["id"].tolist() == ["00456", "00789", "00123", "00123"]
            and processed_frame["name"].iloc[-1] == "Alice",
        )
        pd.testing.assert_frame_equal(app.current_frame, source_frame)

        app.theme_var.set("Graphite")
        app.change_theme("Graphite")
        app.output_format_var.set("csv")
        app.collision_var.set("unique")
        app.log_level_var.set("WARNING")
        app.output_dir_var.set(str(run_dir / "exports"))
        app._persist_workspace()
        evidence.check(
            "Preferences, workflow and rules persisted in isolated folder",
            app.workspace.path.parent.resolve() == (run_dir / "workspace").resolve()
            and app.workspace.store.load_workspace()["settings"]["theme"] == "Graphite",
        )

        cancelled_dir = run_dir / "cancelled-batch"
        gate = CheckpointGate(app).install()
        evidence.check("Cancellable batch accepted", app.run_batch(cancelled_dir))
        pump(app, gate.reached.is_set, description="first durable success checkpoint")
        first_output = Path(gate.snapshot["successes"][0]["output"])
        first_output_hash = digest(first_output)
        app.cancel_job()
        gate.restore()
        idle(app)
        evidence.check(
            "Cancel after first file retains one success and one pending file",
            len(app.last_batch.successes) == 1
            and len(app.last_batch.pending) == 1
            and not app.last_batch.errors
            and app.last_batch.cancelled
            and len(csv_outputs(cancelled_dir)) == 1
            and len(list(cancelled_dir.iterdir())) == 1,
        )
        evidence.check("Cancelled batch retry accepted", app.retry_batch())
        idle(app)
        check_batch_outputs(
            evidence,
            app,
            cancelled_dir,
            first_output,
            first_output_hash,
            "Cancelled batch retry processes only pending source",
        )

        failed_dir = run_dir / "failed-batch"
        second_bytes = second.read_bytes()
        second.write_text(
            "id;name;amount;created_at\n00999;Bob;invalid-number;22/10/2026\n", encoding="utf-8-sig"
        )
        evidence.check("Batch rereads edited sources", app.run_batch(failed_dir))
        idle(app, allow_error=True)
        evidence.check(
            "Changed invalid source produces one success and one failure",
            len(app.last_batch.successes) == len(app.last_batch.errors) == 1
            and not app.last_batch.pending,
        )
        failed_first = Path(app.last_batch.successes[0]["output"])
        failed_hash = digest(failed_first)
        second.write_bytes(second_bytes)
        evidence.check("Failed batch retry accepted after source repair", app.retry_batch())
        idle(app)
        check_batch_outputs(
            evidence,
            app,
            failed_dir,
            failed_first,
            failed_hash,
            "Failed retry processes only repaired source",
        )
        evidence.check(
            "Source hashes unchanged after validation, processing and source repair",
            all(digest(path) == expected for path, expected in source_hashes.items()),
            source_sha256=source_hashes,
        )

        # Leave an actual worker suspended after durable first-success metadata.
        # os._exit simulates process loss: no Tk close, worker cancel or final save.
        interrupted_dir = run_dir / "interrupted-batch"
        gate = CheckpointGate(app).install()
        evidence.check("Hard-stop batch accepted", app.run_batch(interrupted_dir))
        pump(app, gate.reached.is_set, description="hard-stop durable checkpoint")
        interrupted_first = Path(gate.snapshot["successes"][0]["output"])
        interrupted_job = app.workspace.get_job(gate.job_id)
        evidence.check(
            "Hard stop occurs with persisted running job and one pending input",
            interrupted_job["status"] == "running"
            and len(interrupted_job["checkpoint"]["successes"]) == 1
            and len(interrupted_job["checkpoint"]["pending"]) == 1,
        )
        app._persist_workspace()
        evidence.data.update(
            {
                "passed": True,
                "pid": os.getpid(),
                "sources": [str(first), str(second)],
                "source_sha256": source_hashes,
                "workflow": app.collect_config(),
                "rules": app.validation_rules,
                "import_options": app.import_options,
                "preferences": {
                    name: variable.get() for name, variable in app.preference_variables().items()
                },
                "history_count": len(app.history),
                "interrupted_job_id": gate.job_id,
                "interrupted_output_dir": str(interrupted_dir),
                "interrupted_first_output": str(interrupted_first),
                "interrupted_first_sha256": digest(interrupted_first),
                "callback_errors": app._smoke_callback_errors,
            }
        )
        durable_json(run_dir / "phase1.json", evidence.data)
        print(
            "Phase 1 checks passed; hard-stopping after persisted first-file checkpoint.",
            flush=True,
        )
        sys.stderr.flush()
        hard_stop = True
        os._exit(0)
    finally:
        if not hard_stop:
            if gate is not None:
                gate.restore()
            if app.busy:
                app.cancel_job()
                idle(app, allow_error=True)
            app._close()


def phase_two(run_dir, *, hold):
    original = json.loads((run_dir / "phase1.json").read_text(encoding="utf-8"))
    evidence = Evidence("after-process-restart")
    app = new_app()
    try:
        evidence.check("Restart uses a different Python process", os.getpid() != original["pid"])
        evidence.check(
            "Saved files do not autoload on startup", app.files == [] and app.current_frame is None
        )
        restored_preferences = {
            name: variable.get() for name, variable in app.preference_variables().items()
        }
        evidence.check(
            "All preferences restore, including Graphite theme",
            restored_preferences == original["preferences"],
        )
        evidence.check(
            "Workflow, import schema and validation rules survive process loss",
            app.collect_config() == original["workflow"]
            and app.import_options == original["import_options"]
            and app.validation_rules == original["rules"],
        )
        evidence.check(
            "History survives process restart",
            len(app.history) >= original["history_count"]
            and any(event["action"] == "Validation" for event in app.history),
        )
        interrupted_id = original["interrupted_job_id"]
        job = app.workspace.get_job(interrupted_id)
        evidence.check(
            "Startup marks unfinished job interrupted and retains successful checkpoint",
            app.last_batch_job_id == interrupted_id
            and job["status"] == "interrupted"
            and len(job["checkpoint"]["successes"]) == len(job["checkpoint"]["pending"]) == 1,
        )
        evidence.check("Explicit workspace restore accepted", app.restore_workspace())
        idle(app)
        evidence.check(
            "Explicit restore reloads both files using saved text schema",
            len(app.files) == 2
            and app.current_frame["id"].tolist() == ["00123", "00456", "00123", "00789"],
        )
        evidence.check("Interrupted batch retry accepted", app.retry_batch(interrupted_id))
        idle(app)
        evidence.check(
            "Interrupted retry records a new job with safe collision policy",
            app.last_batch_job_id != interrupted_id
            and app.workspace.get_job(app.last_batch_job_id)["payload"]["collision"] == "error",
        )
        check_batch_outputs(
            evidence,
            app,
            original["interrupted_output_dir"],
            original["interrupted_first_output"],
            original["interrupted_first_sha256"],
            "Interrupted retry retains prior successful output",
        )
        evidence.check(
            "Source files remain byte-for-byte unchanged after restart and replay",
            all(digest(path) == expected for path, expected in original["source_sha256"].items()),
            source_sha256=original["source_sha256"],
        )
        evidence.check("Final validation accepted", app.run_validation())
        idle(app)
        evidence.check(
            "Final validation still identifies three rejected original records",
            app.quality_report.summary()["invalid_rows"] == 3,
        )
        app.show_page("Data Validation")
        app.title("DataFlow Studio — 1.2 Verification")
        app.update()
        evidence.check("No Tk callback exceptions", not app._smoke_callback_errors)
        evidence.data.update(
            {
                "passed": True,
                "pid": os.getpid(),
                "final_title": app.title(),
                "final_page": app.page_name,
                "window_held": hold,
                "callback_errors": app._smoke_callback_errors,
            }
        )
        durable_json(run_dir / "phase2.json", evidence.data)
        print("Phase 2 passed; verification window ready.", flush=True)
        if hold:
            pump(
                app, FINISH_SIGNAL.exists, description="finish-production-smoke.signal", timeout=900
            )
    finally:
        if app.busy:
            app.cancel_job()
            idle(app, allow_error=True)
        app._close()


def orchestrate(*, hold):
    run_dir = ARTIFACTS / f"run-{uuid4().hex[:12]}"
    run_dir.mkdir(parents=True)
    env = dict(os.environ)
    env.update(
        {
            "DATAFLOW_WORKSPACE_DIR": str(run_dir / "workspace"),
            "LOCALAPPDATA": str(run_dir / "local-app-data"),
            "PYTHONPATH": str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )
    if hold:
        FINISH_SIGNAL.unlink(missing_ok=True)
    report = {
        "passed": False,
        "desktop": True,
        "synthetic_data": True,
        "run_directory": str(run_dir),
        "workspace_directory": env["DATAFLOW_WORKSPACE_DIR"],
        "local_app_data": env["LOCALAPPDATA"],
        "process_restart": True,
        "phases": [],
    }
    child = None
    try:
        with (run_dir / "phase1.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--phase",
                    "1",
                    "--run-directory",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=180,
                check=False,
            )
        if result.returncode != 0 or not (run_dir / "phase1.json").exists():
            raise AssertionError(
                f"Phase 1 failed (exit {result.returncode}); see {run_dir / 'phase1.log'}"
            )
        report["phases"].append(json.loads((run_dir / "phase1.json").read_text(encoding="utf-8")))
        with (run_dir / "phase2.log").open("w", encoding="utf-8") as log:
            arguments = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--phase",
                "2",
                "--run-directory",
                str(run_dir),
            ]
            if hold:
                arguments.append("--hold")
            child = subprocess.Popen(
                arguments, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
            deadline = time.monotonic() + 180
            while not (run_dir / "phase2.json").exists():
                if child.poll() is not None:
                    raise AssertionError(
                        f"Phase 2 failed (exit {child.returncode}); see {run_dir / 'phase2.log'}"
                    )
                if time.monotonic() >= deadline:
                    raise TimeoutError("Phase 2 did not publish evidence within 180 seconds")
                time.sleep(0.05)
            report["phases"].append(
                json.loads((run_dir / "phase2.json").read_text(encoding="utf-8"))
            )
            report["passed"] = all(phase["passed"] for phase in report["phases"])
            durable_json(ARTIFACTS / "verification.json", report)
            durable_json(run_dir / "verification.json", report)
            print(
                json.dumps(
                    {
                        "passed": report["passed"],
                        "verification": str(ARTIFACTS / "verification.json"),
                        "window_held": hold,
                        "finish_signal": str(FINISH_SIGNAL),
                    },
                    indent=2,
                ),
                flush=True,
            )
            code = child.wait(timeout=930 if hold else 30)
            if code != 0:
                raise AssertionError(f"Phase 2 did not close cleanly (exit {code})")
        report["clean_exit"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        durable_json(ARTIFACTS / "verification.json", report)
        durable_json(run_dir / "verification.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hold", action="store_true", help="Keep final verification window visible."
    )
    parser.add_argument("--phase", choices=["1", "2"], help=argparse.SUPPRESS)
    parser.add_argument("--run-directory", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.phase is not None:
        if args.run_directory is None:
            parser.error("Internal child phase requires --run-directory")
        run_dir = args.run_directory.resolve()
        if not run_dir.is_relative_to(ARTIFACTS.resolve()):
            parser.error("Child artifacts must stay inside gui-production-smoke")
        expected_workspace = run_dir / "workspace"
        expected_local = run_dir / "local-app-data"
        if (
            Path(os.environ.get("DATAFLOW_WORKSPACE_DIR", "")).resolve() != expected_workspace
            or Path(os.environ.get("LOCALAPPDATA", "")).resolve() != expected_local
        ):
            parser.error("Child environment is not isolated")
        if args.phase == "1":
            phase_one(run_dir)
        else:
            phase_two(run_dir, hold=args.hold)
    else:
        orchestrate(hold=args.hold)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
