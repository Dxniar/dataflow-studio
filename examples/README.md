# Synthetic customer fixtures

Every record is generated. Email addresses use the reserved `.test` domain. The workbooks contain no real customer information.

Regenerate with `python scripts/generate_demo_data.py`.

- `customers_dirty.csv` and `.xlsx`: 153 rows, six columns, 132 unique customer IDs, 18 duplicate records and three fully empty rows. Blank records are deliberately placed inside the table.
- `customers_part_a.csv` and `customers_part_b.csv`: 66 unique records each, compatible schemas.
- Workbook sheets: `Customers` (data) and `About` (notice).
- `demo_config.json`: explicit cleanup, city mapping, missing value filling, numeric conversion, rename and sort.
- `filter_config.json`: keep amounts greater than 500 and sort descending.

Run `python scripts/run_demo.py` to produce and verify actual outputs under `examples/output/`. Repeat runs keep previous exports using unique names; the latest metadata report replaces only its own generated JSON report.
