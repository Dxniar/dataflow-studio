# Changelog

## 1.2.0

- Added strict CSV/XLSX import schemas with stored text IDs, explicit dates and decimal/thousands separators.
- Added bounded imports and source-change detection, including file/header/sheet-discovery guards.
- Added read-only validation rules and rejected-record exports with source record numbers and reasons.
- Persisted preferences, workflow/rules, recent paths, history and batch checkpoints locally in SQLite, without table snapshots.
- Added cooperative cancellation, stage progress, failed/pending-only retry and recovery after process interruption.
- Made interrupted recovery fail closed on existing destinations, retaining inherited checkpoints before workers start.
- Added native two-process GUI verification, including a deliberate hard stop and output/source hash checks.
- Added CLI import-config support and `validate` with rejected-row exports and exit code 4 for validation findings.

## 1.1.0

- Redesigned the desktop as a compact data workspace with grouped navigation and consistent line icons.
- Replaced the promotional banner and large metric tiles with a quiet summary strip and larger tables.
- Added row numbers, content-based column widths, dark scrollbars and a guided empty state.
- Replaced the permanent JSON preview with readable workflow steps and a separate JSON inspector.
- Simplified transformation forms, comparison controls and settings layouts for smaller windows.
- Fixed destroyed Tk variable finalization on background threads and added a real desktop lifecycle check.

## 1.0.0

- Shared CSV/XLSX processing engine with explicit cleaning and transformation operations.
- CustomTkinter desktop workflow and Typer CLI.
- Validated JSON pipelines, source protection and unique batch exports.
- Before/after metrics and bounded previews.
- Synthetic multilingual fixtures, automated tests, CI and Windows packaging.
- Documentation and real application demonstration materials.
