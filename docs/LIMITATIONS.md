# Known limitations

- Entire input files and before/after copies are held in memory. A 100-row preview limits rendering work, not RAM use. Large files should be split before processing; there is no streaming engine, cancellation or recovery of an interrupted job.
- XLSX is treated as tabular data. Styles, merged cells, charts, macros, data validation, multiple-sheet workbook structure and original formulas are not preserved in exports. The selected worksheet becomes one output table.
- Formulas are never evaluated. Read values may depend on the last cached result saved by a spreadsheet program. Formula-like strings in exports are protected as text; CSV escaping adds a leading apostrophe and therefore intentionally changes those text values.
- CSV has no schema. pandas infers types during import, so numeric-looking identifiers can lose leading zeros before any pipeline operation. Review the imported data; an explicit import schema is planned. Type conversions, dates and time zones need deliberate handling.
- Only `.csv` and `.xlsx` are supported. `.xls`, `.xlsm`, password-protected workbooks and remote URLs are outside scope.
- Headers must be nonempty and unique. Normalization or renaming that would produce collisions is rejected rather than silently merging columns.
- Filters are literal conditions combined with AND. There is no SQL/query language, expression evaluation, fuzzy matching, or relational JOIN. Merge appends rows using strict, union, or intersection schemas.
- Standardization is an exact value mapping. It does not guess whether similarly spelled values refer to the same business entity.
- Batch is sequential and reports per-file failures. It is not a transaction across all files. Successful outputs remain when another file fails.
- An output directory on a local filesystem is recommended. Cloud sync, network filesystem behavior and external programs racing to modify files are outside the validated environment.
- The GUI supports a single active job. History and settings describe the current session. A rotating metadata log is stored under `%LOCALAPPDATA%/DataFlowStudio/logs/dataflow.log` on Windows (1 MB plus two backups); table cells are excluded. Settings shows the actual path and logging level.
- The Windows distribution is a portable folder, not an installer or signed executable. Keep its `_internal` folder beside the EXE. OS trust prompts can occur for unsigned builds.
- This is an AI-assisted personal portfolio demo with synthetic data, not evidence of a paid client engagement or independent certification.
