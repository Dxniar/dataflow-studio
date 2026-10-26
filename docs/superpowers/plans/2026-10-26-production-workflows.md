# Reliable Desktop Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Deliver the four approved workflow reliability improvements in DataFlow Studio.
**Architecture:** Extend the shared core using separate import, quality and job-control modules. Keep local persistence in a small SQLite service, with GUI forms consuming these interfaces and the CLI retaining compatibility.
**Tech Stack:** Python 3.11+, pandas/openpyxl, SQLite, CustomTkinter, Typer, pytest.
**Spec:** `docs/superpowers/specs/2026-10-26-production-workflows.md`.

## Global Constraints

- Existing exports retain atomic publication, source protection and spreadsheet text protection.
- No destructive source edits, no remote service, no telemetry and no raw table cells in persistent state/logs.
- Existing `PipelineConfig` transformation JSON remains unchanged and compatible.
- Preserve the current design and existing GUI public methods. No installer/signing work.
- Workers never touch Tk objects. IO errors remain sanitized.
- Use original workspace venv through `.superpowers/run_python.cjs`; it sets this worktree's `src` first on PYTHONPATH. No dependencies need installing.

## Review Focus

1. Leading zeroes, blank vs zero and literal NA values survive text import; malformed conversion fails without leaking values.
2. Corrupt/unsupported persisted state recovers safely and does not lose the original database silently.
3. Cancellation immediately before publication cannot expose a partial export; cancellation after a completed file preserves success.
4. Missing columns, empty tables and colliding diagnostic column names yield correct quality reports.
5. Interrupted batch replay retains successes, uses snapshotted options and processes only outstanding inputs.

## Shared Interfaces

### Import and quality (Task 1)

`core.importing.ImportOptions`: dataclass with `column_types: dict[str,str]`, `date_formats: dict[str,str]`, `decimal: str='.'`, `thousands: str|None=None`, `max_file_mb: int=50`, `max_table_mb: int=64`, `max_rows: int=500000`, `max_cells: int=2000000`. Strict `from_dict`, `from_json`, `to_dict`. Types: string/integer/float/datetime/boolean. Unknown columns in explicit schema fail. Limits are safety guards, not supported-size benchmarks.

`io.read_columns(path, *, sheet=0, encoding='utf-8-sig', delimiter=',') -> list[str]` reads only header for the import dialog.
`io.read_table(..., import_options: ImportOptions|dict|None=None, control=None)` preserves existing defaults when options omitted, with bounded safe import. `io.write_table(..., control=None)` checkpoints during serializing and immediately BEFORE atomic publication; never checkpoints after a successful publication. Agent 1 owns all io.py edits.

`core.quality.ValidationRules`: strict `from_dict`, `from_json`, `to_dict`; keys `required_columns:list[str]`, `required_values:list[str]`, `unique_columns:list[str]`, `allowed_values:dict[str,list]`, `numeric_ranges:dict[str,dict]`, `date_ranges:dict[str,dict]`. Bounds min/max optional, min<=max, date ISO; missing values handled by required_values rather than range checks.
`validate_data(frame, rules, *, control=None) -> QualityReport` checks source without mutation.
`QualityReport.summary() -> dict` with `rows`, `valid_rows`, `invalid_rows`, `issue_count`, `schema_errors`.
`QualityReport.issues: DataFrame` and `QualityReport.problem_rows: DataFrame`, the latter contains original invalid records with unique metadata columns for source record number (header=1) and readable reasons. Missing required columns are schema errors; all actual records are invalid in that case. Empty input with missing columns must still report schema errors. No raw values in diagnostics.

### Persistence (Task 2)

`services.workspace.WorkspaceStore(directory: Path|None=None)`. Default env `DATAFLOW_WORKSPACE_DIR` else `%LOCALAPPDATA%/DataFlowStudio` (platform fallback). SQLite uses short per-call connections/transactions, safe for worker callbacks.
`load_workspace()->dict`, `save_workspace(payload:dict)`, `append_history(action, detail, *, timestamp=None)`, `history(limit=200)->list[dict]` (`time`, `action`, `detail`), `create_job(kind,payload)->str`, `update_job(job_id,status,*,checkpoint=None,error=None)`, `get_job(job_id)->dict|None`, `list_jobs(limit=30)->list[dict]`, `mark_interrupted()->int`. Job dict: id/kind/status/payload/checkpoint/error/created_at/updated_at. `.warning` and `.path` expose recovery warning/location. Corrupt DB backed up uniquely in same directory before creating fresh DB. Mark running/cancel_requested interrupted on startup. Store JSON only and cap metadata sizes, never table cells.

### Job control and processor (Task 3)

`core.jobs.JobCancelled(DataFlowError)`.
`ProgressEvent(stage:str, completed:int, total:int, message:str='')` with progress fraction property.
`JobControl(progress_callback=None)`: `cancel()`, `checkpoint()`, `report(stage,completed,total,message='')`, `.cancelled` property. Cancel is thread-safe Event. `file_fingerprint(path,control=None)->dict` safe metadata+SHA256 helper if needed.

Processor adds optional keyword `control=None` to frame/file/merge/batch, and `import_options=None` to all file-reading orchestration. Existing defaults unchanged. Use checkpoint before/after each transform, report meaningful stage counts. Batch accepts `checkpoint_callback: Callable[[BatchResult],None]|None` and `resume_from: BatchResult|dict|None`. `BatchResult` retains successes/errors and adds `pending:list[str]`, `cancelled:bool`; `summary()` retains old keys when no cancellation/pending for old exact tests, may add cancellation fields only when relevant. `to_dict()/from_dict()` round trip strict enough for persisted checkpoints. Batch retries only prior errors+pending, keeps prior successes, callbacks after each completed file and on interruption. Never swallow JobCancelled as ordinary per-file error. When cancellation is requested after export publication, retain success then stop before next input.

## Task 1: Typed import and quality reports

**Files:** create core/importing.py, core/quality.py; modify core/io.py; tests/test_importing.py, tests/test_quality.py, tests/test_core_io.py.
- [x] Add meaningful failing tests for leading-zero CSV/XLSX IDs, European decimals, explicit dates, bad conversions, unknown columns and import limits.
- [x] Implement import types/header read and cooperative IO checkpoints, preserve safe export.
- [x] Add failing tests for every rule, missing schema/empty table, reserved-name collision, input immutability and exact rejected-row export.
- [x] Implement QualityReport and strict rules; run focused then full suite, report failures caused by in-flight work separately.

## Task 2: Local workspace persistence

**Files:** create services/__init__.py, services/workspace.py and tests/test_workspace.py.
- [x] Add failing tests for restart roundtrip, history ordering, job checkpoint persistence, startup interruption and corrupted DB backup.
- [x] Implement local store interface, defensive metadata validation, transactional writes and safe recovery.
- [x] Run focused then full suite. Root integrates GUI. Do not edit app/controller/pages.

## Task 3: Cooperative control and resumable batch

**Files:** create core/jobs.py; modify core/processor.py; tests/test_jobs.py and tests/test_core_processing.py.
- [x] Add failing tests for control cancellation, stage progress, cancellation between transforms/files and partial output preservation.
- [x] Implement control and processor changes, forwarding import settings/control to IO.
- [x] Add failing tests for mixed failure retry, checkpoint roundtrip, cancellation after publication, duplicate input rejection/deduplication and resume preserving successes.
- [x] Implement resume/checkpoints. Run focused and full tests; no io.py edits (Task 1 owns it).

## Task 4: GUI, CLI and release integration (root)

**Files:** gui/app.py, gui/controller.py, gui/pages.py; new gui/import_dialog.py, gui/quality_page.py, gui/workspace_actions.py as useful; cli.py; tests/test_gui_logic.py, tests/test_cli.py; scripts/gui_smoke.py and new native smoke.
- [x] Test control runner cancellation/progress, persisted workflow recovery and safe state callbacks before implementation.
- [x] Add typed import dialog and editable saved schema, data validation page, rejected-row export, persistent preference/history UI, recent-workspace restore and job resume/retry actions.
- [x] Add CLI validation and import-config support using shared core, retain command compatibility.
- [x] Run all tests/lint; execute actual desktop flows for typed import, validation export, restart, cancelled/interrupted batch and retry-only behavior with source hashes.
- [x] Build and launch Windows 1.2 package, update docs and validation evidence. Finish in original checkout after merging verified branch; preserve user outputs.

## Execution ledger

- Ruling: user explicitly approved items 1-4 and previously authorized autonomous engineering decisions; proceed without another design/plan approval prompt.
- Ruling: parallel implementers have disjoint file ownership and fixed interfaces; root handles all GUI integration and shared reviews.
- Baseline: 103 tests passed. Final local suite: 266 passed. Native GUI and two-process interruption/recovery passed. Packaged EXE startup passed. Independent review cleared after two P2 fixes. Integration into the original checkout and publication are the final execution actions.
