# Architecture

```text
Typer CLI ──────────┐
                   ├── Core processor ── pandas transformations
CustomTkinter GUI ─┘         │
  controller + queue         ├── validated JSON configuration
                             └── CSV/XLSX reader + safe exporter
```

The core has no Tk or Typer dependency. Every operation returns a separate DataFrame and factual metadata. The original in-memory frame remains available for comparison. Reading and exporting are separate so a failed or experimental pipeline does not write files.

`core/configuration.py` validates supported keys, value types, mappings and conditions. `core/processor.py` orchestrates transformations, metrics, file and batch operations. `core/io.py` owns encoding, sheets, headers, formula handling and output collision protection. `gui/controller.py` provides headless presentation logic; `gui/app.py` manages the UI. `cli.py` parses terminal options and formats metadata and errors.

## Pipeline order

1. Trim whitespace in string cells.
2. Drop entirely empty rows.
3. Normalize column names.
4. Standardize values with explicit mappings.
5. Fill missing values.
6. Convert types.
7. Remove duplicates, optionally using a column subset.
8. Rename columns.
9. Drop columns.
10. Select columns.
11. Reorder columns.
12. Filter rows (all conditions must match).
13. Sort.

Column references use the names present at that stage. For example, deduplication uses the pre-rename names while filters and sorting use the renamed names. No operation runs unless enabled. Invalid column references are checked during the in-memory pipeline; no output is written on failure.

## Concurrency

Expensive GUI jobs run in worker threads. A thread-safe queue carries completed values or errors; the Tk main thread polls it with `after()`. The UI owns all widget mutations and disables competing actions while work is running. Indeterminate progress avoids fabricated percentages. The preview is bounded, but the underlying DataFrame is not streamed.

## Safety boundary

Output uses a temporary file in the destination directory followed by a collision-safe publish. The source path is protected even if the user chooses the same output name. Existing files are rejected or assigned a numbered filename. There is deliberately no force-overwrite option. CSV formula-looking text is escaped; XLSX strings are written as text. Logs store metadata, never table cells. Configuration supports a finite set of operations and never evaluates Python expressions.

## Tests

Core tests use small real files and transformations. CLI tests invoke Typer and compare exported data. GUI controller tests run without a display. A separate real desktop smoke script exercises the GUI on Windows; it is not required in headless CI. CI covers Windows/Linux and Python 3.11–3.13.

## Dependencies and reference documentation

- [pandas CSV reading](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html)
- [pandas Excel reading](https://pandas.pydata.org/docs/reference/api/pandas.read_excel.html)
- [CustomTkinter packaging guidance](https://customtkinter.tomschimansky.com/documentation/packaging/)
- [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html)

The implementation targets pandas 2.x and is validated against the versions recorded in `docs/VALIDATION.md`.
