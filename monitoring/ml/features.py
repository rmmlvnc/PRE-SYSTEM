"""Shared feature engineering for DengueWatch training and inference."""

import numpy as np
import pandas as pd


BLOOD_TYPES = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
BLOOD_TYPE_COLUMNS = [f"blood_{value.replace('+', '_positive').replace('-', '_negative').lower()}_share" for value in BLOOD_TYPES]

RAW_COLUMNS = [
    "barangay",
    "year",
    "month",
    "case_count",
    "rainfall_mm",
    "temperature_c",
    "humidity_pct",
    *BLOOD_TYPE_COLUMNS,
]

FEATURES = [
    "barangay",
    "year",
    "month",
    "case_count",
    "rainfall_mm",
    "temperature_c",
    "humidity_pct",
] + [
    "cases_lag_1",
    "cases_lag_2",
    "cases_lag_3",
    "cases_lag_6",
    "cases_lag_12",
    "cases_roll_3",
    "cases_roll_6",
    "month_sin",
    "month_cos",
] + [f"{column}_lag_1" for column in BLOOD_TYPE_COLUMNS]


def validate_monthly_data(data: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize barangay-month input data."""

    missing = sorted(set(RAW_COLUMNS) - set(data.columns))

    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}"
        )

    frame = data[RAW_COLUMNS].copy()

    frame["barangay"] = (
        frame["barangay"]
        .astype(str)
        .str.strip()
    )

    numeric_columns = [
        column
        for column in RAW_COLUMNS
        if column != "barangay"
    ]

    frame[numeric_columns] = frame[numeric_columns].apply(
        pd.to_numeric,
        errors="coerce",
    )

    frame = frame.dropna(
        subset=[
            "barangay",
            "year",
            "month",
            "case_count",
        ]
    )

    frame = frame[frame["barangay"] != ""]

    frame["year"] = frame["year"].astype(int)
    frame["month"] = frame["month"].astype(int)

    if not frame["month"].between(1, 12).all():
        raise ValueError(
            "Month values must be between 1 and 12."
        )

    if (frame["case_count"] < 0).any():
        raise ValueError(
            "Case counts cannot be negative."
        )

    duplicate_columns = [
        "barangay",
        "year",
        "month",
    ]

    if frame.duplicated(duplicate_columns).any():
        raise ValueError(
            "Duplicate barangay/year/month rows were found."
        )

    frame["period"] = pd.to_datetime(
        {
            "year": frame["year"],
            "month": frame["month"],
            "day": 1,
        }
    )

    return frame.sort_values(
        ["barangay", "period"]
    ).reset_index(drop=True)


def engineer_features(
    data: pd.DataFrame,
    include_target: bool = True,
) -> pd.DataFrame:
    """Create historical case features without future leakage."""

    frame = validate_monthly_data(data)

    grouped_cases = frame.groupby(
        "barangay",
        sort=False,
    )["case_count"]

    for lag in (1, 2, 3, 6, 12):
        frame[f"cases_lag_{lag}"] = grouped_cases.shift(lag)

    # Patient blood types are aggregated to barangay-month proportions and
    # shifted one period. This prevents current/future patient data from
    # leaking into a next-month case-count forecast.
    for column in BLOOD_TYPE_COLUMNS:
        frame[f"{column}_lag_1"] = frame.groupby("barangay", sort=False)[column].shift(1)

    frame["cases_roll_3"] = grouped_cases.transform(
        lambda values: (
            values.shift(1)
            .rolling(3, min_periods=1)
            .mean()
        )
    )

    frame["cases_roll_6"] = grouped_cases.transform(
        lambda values: (
            values.shift(1)
            .rolling(6, min_periods=1)
            .mean()
        )
    )

    frame["month_sin"] = np.sin(
        2 * np.pi * frame["month"] / 12
    )

    frame["month_cos"] = np.cos(
        2 * np.pi * frame["month"] / 12
    )

    if include_target:
        frame["target_next_cases"] = grouped_cases.shift(-1)

    return frame
