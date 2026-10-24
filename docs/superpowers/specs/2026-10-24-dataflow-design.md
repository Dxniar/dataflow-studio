# DataFlow Studio design

An AI-assisted portfolio demo for local Excel/CSV automation using synthetic small-business data. The user supplied a complete specification and explicitly delegated ordinary engineering decisions and implementation without stepwise confirmations.

## Design
Python 3.11+, pandas/openpyxl, CustomTkinter, Typer. A small service layer shares all data processing between GUI and CLI. No web server or database. Data is held in memory, previews limited to 100 rows. Processing is opt-in and returns a new frame plus factual metrics. GUI background workers communicate through a queue polled by Tk's main thread.

## Approaches
A shared pure transformation engine with file services is selected: easy to test headlessly and consistent between interfaces. Embedding pandas in event handlers would duplicate CLI logic. A web frontend would violate the requested desktop stack.

## Data and safety
Read CSV/XLSX, configure sheet, encoding, delimiter. Preserve source files, reject overwrite by default, reserve unique batch outputs, use temporary output in the destination directory. Formula-looking strings are exported as text; input workbooks are data sources, not executable code. Logs contain metadata only. Document pandas inference, workbook formatting/formula loss, and memory limits.

## User experience
Dark navy sidebar and surfaces with green primary and blue secondary accents. Pages: Dashboard, Data Cleaning, Transform Data, Merge Files, Convert Files, Before / After, History & Logs, Settings. A shared bounded preview table exposes row/column/missing counts. An explicit Run applies selected operations; Export is a separate action. Batch reports per-file successes and failures.

## Acceptance
All requested core operations, meaningful validation, CLI commands, genuine GUI screenshots, deterministic demo, pytest, Ruff, Windows packaging/build smoke, documentation, publication if possible and a portable source ZIP. No invented clients, qualifications, metrics, or demo states. Video uses actual application frames or an honest recording kit if unavailable.
