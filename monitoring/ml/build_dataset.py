"""Build a barangay-month dengue/weather dataset for model training.

Weather is retrieved from Open-Meteo's Historical Weather API for the Iligan
City centre. Keep the generated metadata file with research records so the
source, coordinates, variables, and retrieval time remain auditable.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

try:
    from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay
    from monitoring.ml.features import BLOOD_TYPES, BLOOD_TYPE_COLUMNS
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from monitoring.locations import ILIGAN_BARANGAYS, canonicalize_barangay
    from monitoring.ml.features import BLOOD_TYPES, BLOOD_TYPE_COLUMNS

ILIGAN_LATITUDE = 8.2280
ILIGAN_LONGITUDE = 124.2452


def read_cases(dataset_dir: Path) -> pd.DataFrame:
    """Read the corrected workbook when present, otherwise use legacy CSVs."""
    records = []
    workbooks = sorted(dataset_dir.glob('dengue_organized_*.xlsx'))
    if workbooks:
        for path in workbooks:
            for sheet in pd.read_excel(path, sheet_name=None, dtype=object).values():
                for row in sheet.to_dict('records'):
                    barangay = canonicalize_barangay(row.get('(Current Address) Barangay'))
                    date = pd.to_datetime(row.get('DAdmit'), errors='coerce')
                    blood_type = str(row.get('Blood Type') or row.get('Bloodtype') or row.get('BloodType') or '').strip().upper().replace(' ', '')
                    if barangay and pd.notna(date):
                        records.append({'barangay': barangay, 'date': date, 'blood_type': blood_type})
    else:
        for path in sorted(dataset_dir.glob('WILBUR_DSO_dengue_*.csv')):
            with path.open(encoding='utf-8-sig', newline='') as handle:
                for row in csv.DictReader(handle):
                    barangay = canonicalize_barangay(row.get('(Current Address) Barangay'))
                    date_text = (row.get('DAdmit') or '').strip()
                    date = pd.to_datetime(date_text, errors='coerce')
                    blood_type = str(row.get('Blood Type') or row.get('Bloodtype') or row.get('BloodType') or '').strip().upper().replace(' ', '')
                    if barangay and pd.notna(date):
                        records.append({'barangay': barangay, 'date': date, 'blood_type': blood_type})
    if not records:
        raise ValueError('No valid dengue case rows were found.')
    return pd.DataFrame(records)


def fetch_weather(start_date: str, end_date: str) -> tuple[pd.DataFrame, str]:
    params = {
        'latitude': ILIGAN_LATITUDE,
        'longitude': ILIGAN_LONGITUDE,
        'start_date': start_date,
        'end_date': end_date,
        'daily': 'temperature_2m_mean,precipitation_sum',
        'hourly': 'relative_humidity_2m',
        'timezone': 'Asia/Manila',
    }
    url = 'https://archive-api.open-meteo.com/v1/archive?' + urlencode(params)
    with urlopen(url, timeout=90) as response:
        payload = json.load(response)

    daily = pd.DataFrame(payload['daily']).rename(columns={
        'time': 'date', 'temperature_2m_mean': 'temperature_c',
        'precipitation_sum': 'rainfall_mm',
    })
    daily['date'] = pd.to_datetime(daily['date'])
    hourly = pd.DataFrame(payload['hourly']).rename(columns={
        'time': 'date', 'relative_humidity_2m': 'humidity_pct',
    })
    hourly['date'] = pd.to_datetime(hourly['date'])
    humidity = hourly.set_index('date')['humidity_pct'].resample('MS').mean()
    monthly = daily.set_index('date').resample('MS').agg({
        'temperature_c': 'mean', 'rainfall_mm': 'sum',
    })
    monthly['humidity_pct'] = humidity
    return monthly.reset_index(), url


def load_cached_weather(dataset_dir: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Reuse prior monthly weather values when the public provider is unavailable."""
    cache_path = dataset_dir / 'integrated_monthly.csv'
    if not cache_path.is_file():
        raise RuntimeError('No cached weather dataset is available.')
    cached = pd.read_csv(cache_path, usecols=[
        'year', 'month', 'rainfall_mm', 'temperature_c', 'humidity_pct',
    ])
    cached['date'] = pd.to_datetime(dict(year=cached.year, month=cached.month, day=1))
    cached = cached[['date', 'rainfall_mm', 'temperature_c', 'humidity_pct']].dropna().drop_duplicates('date')
    required = pd.date_range(start, end, freq='MS')
    available = set(cached['date'])
    missing = [month.strftime('%Y-%m') for month in required if month not in available]
    if missing:
        raise RuntimeError(f'Cached weather is missing: {", ".join(missing)}.')
    return cached


def build(dataset_dir: Path, output: Path, metadata: Path) -> pd.DataFrame:
    cases = read_cases(dataset_dir)
    cases['month_date'] = cases['date'].dt.to_period('M').dt.to_timestamp()
    start = cases['month_date'].min()
    end = cases['month_date'].max()
    try:
        weather, source_url = fetch_weather(
            start.strftime('%Y-%m-%d'),
            (end + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d'),
        )
        weather_source = 'Open-Meteo Historical Weather API'
        weather_note = None
    except Exception as error:
        weather = load_cached_weather(dataset_dir, start, end)
        source_url = 'local integrated_monthly.csv weather cache'
        weather_source = 'Cached Open-Meteo weather values'
        weather_note = f'Live weather retrieval failed; reused verified local values: {error}'

    # Build the complete official 44-barangay grid, including zero-case months.
    names = sorted(ILIGAN_BARANGAYS, key=str.casefold)
    months = pd.date_range(start, end, freq='MS')
    grid = pd.MultiIndex.from_product(
        [names, months], names=['barangay', 'month_date']
    ).to_frame(index=False)
    counts = cases.groupby(['barangay', 'month_date']).size().rename('case_count').reset_index()
    result = grid.merge(counts, how='left', on=['barangay', 'month_date'])
    result['case_count'] = result['case_count'].fillna(0).astype(int)
    valid_blood = cases[cases['blood_type'].isin(BLOOD_TYPES)]
    blood_counts = valid_blood.groupby(['barangay', 'month_date', 'blood_type']).size().unstack(fill_value=0)
    blood_counts = blood_counts.reindex(columns=BLOOD_TYPES, fill_value=0).reset_index()
    result = result.merge(blood_counts, how='left', on=['barangay', 'month_date'])
    for blood_type, column in zip(BLOOD_TYPES, BLOOD_TYPE_COLUMNS):
        result[column] = (result[blood_type].fillna(0) / result['case_count'].replace(0, 1)).where(result['case_count'] > 0, 0.0)
    result = result.drop(columns=list(BLOOD_TYPES))
    result = result.merge(weather, how='left', left_on='month_date', right_on='date')
    result['year'] = result['month_date'].dt.year
    result['month'] = result['month_date'].dt.month
    result = result[[
        'barangay', 'year', 'month', 'case_count', 'rainfall_mm',
        'temperature_c', 'humidity_pct', *BLOOD_TYPE_COLUMNS,
    ]]
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    metadata.write_text(json.dumps({
        'source': weather_source,
        'source_url': source_url,
        'coordinates': {'latitude': ILIGAN_LATITUDE, 'longitude': ILIGAN_LONGITUDE},
        'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
        'weather_scope': 'One city-level grid point applied to all barangays',
        'limitations': 'Reanalysis/model weather; validate against PAGASA observations when available.',
        'location_scope': '44 official City of Iligan barangays (PSGC)',
        'psgc_source': 'https://psa.gov.ph/classification/psgc/barangays/1030900000',
        'rows': len(result),
        'weather_retrieval_note': weather_note,
    }, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument('--datasets', type=Path, default=root / 'datasets')
    parser.add_argument('--output', type=Path, default=root / 'datasets' / 'integrated_monthly.csv')
    parser.add_argument('--metadata', type=Path, default=root / 'datasets' / 'weather_source.json')
    args = parser.parse_args()
    frame = build(args.datasets, args.output, args.metadata)
    print(f'Created {args.output} with {len(frame)} rows.')
