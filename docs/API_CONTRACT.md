# Internal integration contract

Public imports (all paths under `src/dataflow`):

```python
from dataflow.core.configuration import PipelineConfig
from dataflow.core.processor import (
    process_frame,
    process_file,
    batch_process,
    merge_files,
    ProcessingResult,
    BatchResult,
)
from dataflow.core.io import read_table, write_table, list_sheets
from dataflow.core.errors import DataFlowError
```

- `PipelineConfig.from_dict(data: dict) -> PipelineConfig`, `from_json(path)`, `to_dict()`; unknown keys and wrong values raise DataFlowError.
- `read_table(path, *, sheet=0, encoding='utf-8-sig', delimiter=',') -> pd.DataFrame`
- `list_sheets(path) -> list[str]`
- `write_table(frame, path, *, encoding='utf-8-sig', delimiter=',', collision='error', source_paths=()) -> Path`. collision = error / unique; NEVER overwrite. XLSX text values cannot become formulas.
- `process_frame(frame, config: PipelineConfig) -> ProcessingResult`
- `process_file(path, config, *, sheet=0, encoding='utf-8-sig', delimiter=',') -> ProcessingResult`
- `merge_files(paths, *, mode='union', sheet=0, encoding='utf-8-sig', delimiter=',') -> ProcessingResult` mode union / strict / intersection.
- `batch_process(paths, config, output_dir, *, output_format='csv', sheet=0, encoding='utf-8-sig', delimiter=',', collision='unique') -> BatchResult`

`ProcessingResult` dataclass fields: `original` DataFrame, `processed` DataFrame, `operations` list[str], `duplicates_removed` int, `elapsed_seconds` float, `files_processed` int (default 1), `source_paths` list[str] (default empty). `summary() -> dict` with `original_rows`, `processed_rows`, `original_columns`, `processed_columns`, `duplicates_removed`, `missing_before`, `missing_after`, `files_processed`, `operations`, `elapsed_seconds`.

`BatchResult` fields `successes: list[dict]` (input, output, summary), `errors: list[dict]` (input, error); `summary() -> dict` with processed/failed/files.

Configuration flat JSON keys and defaults (all optional; operations off by default):

```json
{
  "trim_whitespace": false,
  "drop_empty_rows": false,
  "normalize_columns": false,
  "drop_duplicates": false,
  "deduplicate_by": null,
  "fill_missing": {},
  "standardize_values": {},
  "rename_columns": {},
  "drop_columns": [],
  "select_columns": [],
  "reorder_columns": [],
  "convert_types": {},
  "filters": [],
  "sort_by": [],
  "sort_ascending": true
}
```

`standardize_values`: column -> mapping of old string to new scalar. `convert_types`: column -> string/integer/float/datetime/boolean. Filters: `{ "column": "amount", "operator": "greater_than", "value": 100 }`; operators equals/not_equals/contains/greater_than/less_than/is_empty/is_not_empty. Numeric comparisons validate types, contains is literal (no arbitrary expressions).

Order: trim, empty rows, normalize, standardize, fill, type conversion, deduplicate, rename, drop, select, reorder, filter, sort. References use column names at the operation's point. Invalid references must fail before any externally visible change. Result owns copies; original frame immutable.

GUI public interface: `dataflow.gui.app.DataFlowApp`, `main()`. Public headless controller in `dataflow.gui.controller`: `run_pipeline(frame, config_dict) -> ProcessingResult`. All GUI and CLI operations call core functions. Root owns pyproject, CI, examples, documentation and packaging. Agents own core, GUI, CLI respectively and their tests.
