# Reliable local workflows

DataFlow Studio supports explicit CSV/XLSX import types, source validation, local workspace metadata and cooperative job cancellation. Transformations still use the existing pipeline JSON format; import schemas and validation rules are separate files.

## Import schema

Save this as `import.json` for a semicolon-separated source containing the named columns:

```json
{
  "column_types": {
    "customer_id": "string",
    "quantity": "integer",
    "amount": "float",
    "created_at": "datetime",
    "active": "boolean"
  },
  "date_formats": {"created_at": "%d.%m.%Y"},
  "decimal": ",",
  "thousands": ".",
  "max_file_mb": 50,
  "max_table_mb": 64,
  "max_rows": 500000,
  "max_cells": 2000000
}
```

Explicit string import preserves identifiers such as `00123`, literal `NA` and the distinction between blank text and `0`. Excel text identifiers preserve their characters; a numeric Excel cell cannot recover zeros that exist only in its display format. Supported types are `string`, `integer`, `float`, `datetime` and `boolean`. A named schema column must exist. Invalid conversions fail with a message that omits the offending cell value. Date formats apply to columns declared `datetime`. Without an import schema, the existing default type inference remains available, with bounded import guards.

```powershell
dataflow inspect customers.csv --import-config import.json --delimiter ";"
dataflow process customers.csv --config pipeline.json --import-config import.json --delimiter ";" --output processed.csv
```

`--import-config` is also available on `clean`, `convert`, `merge` and `batch`. The import schema controls reading; export continues to use the selected CSV delimiter/encoding and the output filename extension. Use `--sheet` for an Excel worksheet name or zero-based index; prefix a numeric sheet name with `name:`, for example `--sheet name:2025`.

The guard defaults are 50 MiB for the source file, 64 MiB for measured in-memory table size, 500,000 rows and 2,000,000 cells. These are safety limits, not performance benchmarks or a promise that every file below the limits will fit available memory. Parsing, copies, validation and transformations can require additional memory. Global operations run in memory; this is not a streaming processing engine.

## Source validation and rejected records

Save this as `rules.json`:

```json
{
  "required_columns": ["customer_id", "amount", "created_at"],
  "required_values": ["customer_id", "amount"],
  "unique_columns": ["customer_id"],
  "allowed_values": {"active": [true, false]},
  "numeric_ranges": {"amount": {"min": 0, "max": 1000000}},
  "date_ranges": {"created_at": {"min": "2020-01-01", "max": "2030-12-31"}}
}
```

Bounds are optional and inclusive; minimum cannot exceed maximum. Numeric bounds must be finite and date bounds use ISO dates or date-times. Missing values are handled by `required_values`; uniqueness, allowed-value and range checks skip empty values. Referencing a missing column produces a schema error, including on a header-only source. When a required rule column is missing, all existing source records are rejected. Validation does not mutate the source or apply cleaning rules.

```powershell
dataflow validate customers.csv --rules rules.json --import-config import.json --delimiter ";"
dataflow validate customers.csv --rules rules.json --import-config import.json --delimiter ";" --output rejected.xlsx
```

The command prints a JSON summary containing `rows`, `valid_rows`, `invalid_rows`, `issue_count` and `schema_errors`. An exported report also includes `output`. Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Validation completed without invalid rows or schema errors |
| 4 | Validation completed and found invalid rows or schema errors |
| 1 | Invalid configuration, inaccessible input/output or another processing error |
| 2 | Invalid command arguments |

Without `--output`, validation writes no report file. With it, rejected records retain their source values and receive `_source_record` and `_validation_reasons` columns. Record numbering starts at 2 because the header counts as record 1. If those names already exist, generated metadata names receive a suffix. `issue_count` counts row-level rule violations; schema errors are also reported separately, so a missing-column-only result can have zero row-level issues.

Exports support CSV and XLSX, protect source paths, publish atomically and retain spreadsheet text protection. Existing destinations fail by default; `--collision unique` selects a new output filename. Selecting the source itself as output fails even with the unique collision policy.

## Cancellation and batch recovery

The desktop worker reports stages and completed/total work. Cancel requests are checked between transformations/files and at IO boundaries. A single pandas operation or parser call can finish before the next check; cancellation does not forcibly terminate that operation. Workers do not manipulate Tk widgets.

The exporter checks cancellation immediately before atomic publication. Cancellation at that point leaves no partial published result. Once publication succeeds, that output remains successful even if cancellation arrives immediately afterward. A cancelled batch retains completed outputs and leaves outstanding inputs in its checkpoint.

Batch checkpoints retain successful outputs, per-file errors and pending input paths. Recovery/retry uses the saved transformation, import and IO options, processes failed/pending inputs, and retains prior successes without rereading successful source files. Duplicate input paths are processed once. Retried inputs use their current file contents; source files may have changed since the original run. Missing or invalid retry inputs are reported as failures. Checkpoints are local metadata, not copies of the source data.

Startup marks jobs left `running` or `cancel_requested` as `interrupted`. Recovery requires an explicit user action; recent paths are not automatically loaded into the table. Keep successful output files available when resuming a batch. The CLI `batch` command supports import schemas and keeps its existing partial-failure exit code 3; interactive cancellation/recovery controls belong to the desktop workflow.

After a hard process loss, publication may have completed immediately before its SQLite checkpoint. Interrupted recovery therefore creates a new saved job with collision policy `error`: an existing destination requires review, rather than producing an unverified extra numbered file. Inherited successes and pending paths are persisted before the recovery worker starts. Ordinary retry of a checkpointed failed/cancelled job retains its saved collision policy.

A recoverable batch requires an initial durable checkpoint. If later checkpoint persistence fails (for example, unavailable disk space or a metadata limit), the batch stops after the first undurable outcome. Completed outputs remain intact, and same-session recovery also uses the conservative collision-error policy even if writing an interrupted status fails.

## Local storage and privacy

Normal desktop entry points acquire a nonblocking operating-system lock on `workspace.lock` before opening the workspace or creating the application window. A second instance using the same workspace is refused with a readable message, preventing a live job from being misclassified as interrupted. The lock is released on normal exit or process death. Distinct workspace folders can be used independently.

The SQLite workspace stores settings, workflow configuration, import options, validation rules, recent paths, history and job metadata. It does not store DataFrame cells or source table snapshots. Configuration values, column names, filesystem paths and user-supplied rules can still contain sensitive information; the workspace database is an ordinary local file and is not encrypted by this feature. Logs and diagnostics omit raw cell values. Explicit exported rejected-record files do contain source values and should be handled like the originals.

Default Windows location:

```text
%LOCALAPPDATA%\DataFlowStudio\workspace.sqlite3
```

Set `DATAFLOW_WORKSPACE_DIR` to override the containing folder. Without `LOCALAPPDATA`, the fallback is `~/.local/share/DataFlowStudio`. SQLite connections are short-lived and opened separately for each call, allowing background progress/checkpoint callbacks to save metadata safely.

Each JSON metadata object is limited to 1 MiB, 20,000 values and 24 nested levels; non-finite numbers and non-JSON objects are rejected. Large checkpoints can therefore exceed the metadata limit independently of source import guards. History returns recent entries first, and job lists show the newest jobs first.

A corrupt database is preserved under a unique `workspace.corrupt-<id>.sqlite3` name in the same folder before a fresh database is created. SQLite sidecar files, if present, accompany that backup. An unsupported database version or malformed table schema is preserved, with a warning and unavailable writes instead of silently replacing it. Invalid JSON state falls back safely; malformed job checkpoints are withheld from replay. A backup is a recovery artifact, not an automatic restoration guarantee.
