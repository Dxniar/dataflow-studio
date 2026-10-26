# Reliable desktop workflows

The user approved implementation of the first four readiness improvements: typed import, data quality checks with rejected-row exports, persistent workspace, and cancellable/recoverable jobs. Keep the current desktop design and all existing core/CLI behavior compatible. No server, account system, installer or paid signing is in scope.

## Decisions

- Import settings select types before loading CSV/XLSX and can be applied by reloading the source. Explicit text types preserve leading zeroes. Dates and decimal/thousands separators are explicit. Invalid conversions never silently become missing values.
- Data checks are read-only and separate from transformation rules. Support required columns, nonempty values, uniqueness, allowed values, numeric and date bounds. Show a summary and export source records with readable reasons through the existing safe exporter.
- Store settings, workflow, import options, quality rules, recent paths and run metadata locally in SQLite under the current user's application data folder. Never store table contents. Restore files only on explicit user action; do not silently reload data on startup. Expose a folder override for tests.
- One background job at a time. Cooperative cancellation checks between pandas operations/files and during IO where practical. A single pandas operation may finish before cancellation takes effect. Published output files remain intact. Progress reports stage and completed/total work.
- Persist batch checkpoints after each file. On startup mark unfinished runs interrupted. Retry only failed/pending inputs using saved options and current source contents; keep prior successful outputs and never overwrite sources/results.
- Bounded import: configurable file/table/cell limits with actionable errors, not a streaming-performance claim. Keep global operations in memory and document this.

## Acceptance

Leading-zero CSV/XLSX IDs survive explicit text import. European numbers and explicit dates import correctly. Invalid rules fail clearly; valid rules identify/export the exact rejected records without mutating input. Restart preserves preferences/workflow/history and exposes restorable recent paths. Cancelled batch retains completed outputs and checkpoints; recovery after process interruption can retry only outstanding files. Existing examples/tests remain compatible. GUI and packaged Windows app receive real workflow checks.
