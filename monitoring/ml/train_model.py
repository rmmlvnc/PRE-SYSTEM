"""Train and evaluate DengueWatch's Random Forest forecasting model.

Input must contain one row per barangay/month with these columns:
barangay, year, month, case_count, rainfall_mm, temperature_c, humidity_pct.
The target is the following month's case count in the same barangay.
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

try:
    from .features import FEATURES, engineer_features
except ImportError:  # Allows: python monitoring/ml/train_model.py ...
    from features import FEATURES, engineer_features


def prepare_data(csv_path: Path) -> pd.DataFrame:
    data = engineer_features(pd.read_csv(csv_path), include_target=True)
    return data.dropna(subset=['target_next_cases', 'cases_lag_1']).reset_index(drop=True)


def train(csv_path: Path, output_path: Path, metrics_path: Path) -> dict:
    data = prepare_data(csv_path)
    if len(data) < 50:
        raise ValueError('At least 50 usable barangay-month rows are required.')

    # Split on whole calendar months so a month cannot appear in both sets.
    periods = sorted(data['period'].unique())
    if len(periods) < 6:
        raise ValueError('At least six distinct months are required.')
    cutoff = periods[max(1, int(len(periods) * 0.8))]
    train_data = data[data['period'] < cutoff]
    test_data = data[data['period'] >= cutoff]
    if test_data.empty:
        raise ValueError('The validation set is empty; provide more rows.')

    preprocess = ColumnTransformer([
        ('barangay', OneHotEncoder(handle_unknown='ignore'), ['barangay']),
        ('numeric', SimpleImputer(strategy='median'), FEATURES[1:]),
    ])
    evaluation_pipeline = Pipeline([
        ('preprocess', preprocess),
        ('model', RandomForestRegressor(
            n_estimators=400, random_state=42, min_samples_leaf=3,
            max_features=0.8, n_jobs=-1
        )),
    ])
    evaluation_pipeline.fit(train_data[FEATURES], train_data['target_next_cases'])
    predicted = np.maximum(0, evaluation_pipeline.predict(test_data[FEATURES]))
    actual = test_data['target_next_cases']
    baseline = test_data['case_count'].clip(lower=0)
    metrics = {
        'dataset_rows': int(len(pd.read_csv(csv_path))),
        'usable_rows': int(len(data)),
        'training_rows': int(len(train_data)),
        'test_rows': int(len(test_data)),
        'validation_start': pd.Timestamp(cutoff).strftime('%Y-%m'),
        'mae': round(float(mean_absolute_error(actual, predicted)), 4),
        'rmse': round(float(mean_squared_error(actual, predicted) ** 0.5), 4),
        'r2': round(float(r2_score(actual, predicted)), 4) if len(actual) > 1 else None,
        'persistence_baseline_mae': round(float(mean_absolute_error(actual, baseline)), 4),
        'features': FEATURES,
        'target': 'next-month dengue case count',
        'algorithm': 'RandomForestRegressor',
        'random_state': 42,
        'warning': 'Decision-support forecast; validate with health professionals.',
    }
    # Refit the deployable model on all usable rows after holdout evaluation.
    pipeline = Pipeline([
        ('preprocess', preprocess),
        ('model', RandomForestRegressor(
            n_estimators=400, random_state=42, min_samples_leaf=3,
            max_features=0.8, n_jobs=-1
        )),
    ])
    pipeline.fit(data[FEATURES], data['target_next_cases'])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'pipeline': pipeline, 'metrics': metrics}, output_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', type=Path, help='Integrated monthly CSV dataset')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('random_forest.pkl'))
    parser.add_argument('--metrics', type=Path, default=Path(__file__).with_name('model_metrics.json'))
    args = parser.parse_args()
    print(json.dumps(train(args.csv, args.output, args.metrics), indent=2))
