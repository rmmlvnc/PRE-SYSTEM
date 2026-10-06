"""Normalize an existing monthly dataset to the official Iligan City scope."""

import argparse
from pathlib import Path

import pandas as pd

try:
    from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay
    from monitoring.ml.features import BLOOD_TYPE_COLUMNS
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay
    from monitoring.ml.features import BLOOD_TYPE_COLUMNS


def clean(source: Path, output: Path) -> pd.DataFrame:
    data = pd.read_csv(source)
    data["barangay"] = data["barangay"].map(canonicalize_barangay)
    data = data.dropna(subset=["barangay", "year", "month"])
    data["case_count"] = pd.to_numeric(data["case_count"], errors="coerce").fillna(0)
    for column in BLOOD_TYPE_COLUMNS:
        if column not in data:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0.0)

    cases = data.groupby(["barangay", "year", "month"], as_index=False)["case_count"].sum()
    weather = data.groupby(["year", "month"], as_index=False).agg(
        rainfall_mm=("rainfall_mm", "median"),
        temperature_c=("temperature_c", "median"),
        humidity_pct=("humidity_pct", "median"),
    )
    periods = weather[["year", "month"]].drop_duplicates()
    barangays = pd.DataFrame({"barangay": ILIGAN_BARANGAYS})
    grid = barangays.merge(periods, how="cross")
    result = grid.merge(cases, how="left", on=["barangay", "year", "month"])
    result = result.merge(weather, how="left", on=["year", "month"])
    result["case_count"] = result["case_count"].fillna(0).astype(int)
    blood = data.groupby(["barangay", "year", "month"], as_index=False)[BLOOD_TYPE_COLUMNS].mean()
    result = result.merge(blood, how="left", on=["barangay", "year", "month"])
    result[BLOOD_TYPE_COLUMNS] = result[BLOOD_TYPE_COLUMNS].fillna(0.0)
    result = result.sort_values(["barangay", "year", "month"])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?", default=root / "datasets" / "integrated_monthly.csv")
    parser.add_argument("--output", type=Path, default=root / "datasets" / "integrated_monthly_clean.csv")
    args = parser.parse_args()
    cleaned = clean(args.source, args.output)
    print(f"Created {args.output} with {len(cleaned)} rows and {cleaned['barangay'].nunique()} barangays.")
