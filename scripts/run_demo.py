"""Reproduce cleaning, conversion, merge and batch; verify real results."""

import hashlib
import json
from pathlib import Path

from generate_demo_data import generate

from dataflow.core.configuration import PipelineConfig
from dataflow.core.io import read_table, write_table
from dataflow.core.processor import batch_process, merge_files, process_file

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths = generate()
    source_hashes = {name: digest(path) for name, path in paths.items()}
    output = ROOT / "examples" / "output"
    output.mkdir(parents=True, exist_ok=True)
    config = PipelineConfig.from_json(ROOT / "examples" / "demo_config.json")
    result = process_file(paths["csv"], config)
    assert len(result.original) == 153, result.summary()
    assert len(result.processed) == 132, result.summary()
    assert result.duplicates_removed == 18, result.summary()
    cleaned = write_table(result.processed, output / "customers_clean.xlsx", collision="unique")
    converted = write_table(read_table(cleaned), output / "customers_clean.csv", collision="unique")
    assert len(read_table(converted)) == 132
    merged = merge_files([paths["part_a"], paths["part_b"]], mode="strict")
    assert len(merged.processed) == 132
    merged_path = write_table(merged.processed, output / "customers_merged.csv", collision="unique")
    batch = batch_process(
        [paths["csv"], paths["xlsx"]], config, output / "batch", output_format="xlsx"
    )
    assert len(batch.successes) == 2 and not batch.errors, batch.summary()
    assert all(digest(paths[name]) == value for name, value in source_hashes.items())
    report = {
        "demo": "AI-assisted portfolio demo; synthetic records only",
        "source_files_unchanged": True,
        "cleaning": result.summary(),
        "exports": [str(path.relative_to(ROOT)) for path in [cleaned, converted, merged_path]],
        "batch": batch.summary(),
    }
    (output / "demo_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
