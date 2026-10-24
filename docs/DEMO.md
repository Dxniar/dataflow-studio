# Reproduce the demo

Install the project from the repository root, then run:

```powershell
python scripts/generate_demo_data.py
python scripts/run_demo.py
python -m dataflow
```

The first command recreates synthetic inputs. The second verifies cleaning, two conversion directions, merging, batch processing and source-file hashes. It writes real outputs and `examples/output/demo_report.json`. Existing spreadsheet outputs receive unique names.

## GUI walkthrough

1. On Dashboard, upload `examples/input/customers_dirty.csv`.
2. Inspect the input table. Notice repeated customer IDs, blanks and padding around names and cities.
3. In Data Cleaning enable Trim Whitespace, Remove Empty Rows and Remove Duplicates. Select `customer_id` as the duplicate key.
4. Alternatively load `examples/demo_config.json` to apply the full demonstrated pipeline, including missing-value fills, exact city mappings, numeric conversion, rename and sorting.
5. Run processing. The Before / After screen shows counts computed from this run.
6. Export to a new `.xlsx` file. The original input stays unchanged.
7. Upload `customers_dirty.xlsx`, choose `Customers`, and run the same pipeline in batch to a fresh output directory.
8. Open History & Logs to inspect completion times and export paths.

Expected fixture counts are 153 original rows, 132 processed rows, 18 duplicates removed and 3 empty rows removed. The actual summary is produced by the core; the UI does not hard-code these numbers.

## Screenshots

Images in `assets/screenshots` must come from a real running application. The screen capture and validation record identify the run. Demo files contain English, Russian and Kazakh text and reserved `.test` email addresses.

## Scope of the Upwork offer

This repository demonstrates more features than the Starter package. It does not promise the whole GUI or all operations for $35. Agree on file formats, operations, output layout and acceptance examples before pricing any client work. No portfolio material should describe this demo as a real client project.
