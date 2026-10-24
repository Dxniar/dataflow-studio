"""Deterministic synthetic fixtures; no real customer or contact information."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["customer_id", "full_name", "email", "city", "amount", "created_at"]


def generate(output_dir: Path | None = None) -> dict[str, Path]:
    output_dir = output_dir or ROOT / "examples" / "input"
    output_dir.mkdir(parents=True, exist_ok=True)
    cities = [" Almaty ", "almaty", "ALMATY", "Astana", " astana ", "Қызылорда"]
    records = []
    for index in range(1, 133):
        name = ["Demo Customer", "Демо Клиент", "Демо Тұтынушы"][index % 3]
        records.append(
            {
                "customer_id": f"C{index:04d}",
                "full_name": f"  {name} {index:03d}  ",
                "email": None if index % 11 == 0 else f"customer{index:03d}@example.test",
                "city": cities[(index - 1) % len(cities)],
                "amount": None if index % 17 == 0 else round(25 + (index * 37) % 975, 2),
                "created_at": f"2026-09-{(index - 1) % 28 + 1:02d}",
            }
        )
    # Place exact duplicates and blank records near the top so defects are visible.
    dirty = records[:6] + records[:3] + [{column: None for column in COLUMNS}]
    dirty += records[6:40] + records[3:12]
    dirty += [{column: None for column in COLUMNS}] + records[40:90] + records[12:18]
    dirty += [{column: None for column in COLUMNS}] + records[90:]
    frame = pd.DataFrame(dirty, columns=COLUMNS)
    paths = {
        "csv": output_dir / "customers_dirty.csv",
        "xlsx": output_dir / "customers_dirty.xlsx",
        "part_a": output_dir / "customers_part_a.csv",
        "part_b": output_dir / "customers_part_b.csv",
    }
    frame.to_csv(paths["csv"], index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(paths["xlsx"], engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Customers")
        pd.DataFrame({"notice": ["AI-assisted portfolio demo. Synthetic data only."]}).to_excel(
            writer, index=False, sheet_name="About"
        )
    pd.DataFrame(records[:66]).to_csv(paths["part_a"], index=False, encoding="utf-8-sig")
    pd.DataFrame(records[66:]).to_csv(paths["part_b"], index=False, encoding="utf-8-sig")
    return paths


if __name__ == "__main__":
    for label, path in generate().items():
        print(f"{label}: {path.relative_to(ROOT)}")
