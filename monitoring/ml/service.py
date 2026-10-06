"""Backend inference service used by CHO and LGU prediction pages."""

from calendar import month_name
import csv
from collections import Counter, defaultdict
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta

import joblib
import pandas as pd
from django.conf import settings
from django.core.cache import cache

from .features import BLOOD_TYPES, BLOOD_TYPE_COLUMNS, FEATURES, engineer_features
from monitoring.locations import canonicalize_barangay


def _most_common(counter: Counter, default: str = 'Not available') -> str:
    """Return the most common valid label from a Counter."""
    return counter.most_common(1)[0][0] if counter else default


def _age_group(value: object) -> str | None:
    """Convert a patient age into a readable public-health age group."""
    try:
        age = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if age < 0 or age > 120:
        return None
    if age <= 5:
        return '0–5 years'
    if age <= 12:
        return '6–12 years'
    if age <= 19:
        return '13–19 years'
    if age <= 39:
        return '20–39 years'
    if age <= 59:
        return '40–59 years'
    return '60+ years'


def load_demographic_profiles(dataset_dir: Path) -> tuple[dict, dict]:
    """Summarize observed patient records globally and per barangay.

    These values describe historical records. They are not model predictions
    and must never be presented as personal susceptibility or diagnosis.
    """
    counters = defaultdict(lambda: {
        'blood': Counter(), 'sex': Counter(), 'age': Counter(),
        'purok': Counter(), 'records': 0,
    })
    overall = {
        'blood': Counter(), 'sex': Counter(), 'age': Counter(),
        'purok': Counter(), 'records': 0,
    }

    for path in sorted(dataset_dir.glob('WILBUR_DSO_dengue_*.csv')):
        try:
            with path.open(encoding='utf-8-sig', newline='') as handle:
                for row in csv.DictReader(handle):
                    barangay = canonicalize_barangay(
                        row.get('(Current Address) Barangay')
                        or row.get('Barangay')
                        or row.get('barangay')
                    )
                    if not barangay:
                        continue

                    sex = str(row.get('Sex') or row.get('sex') or '').strip().title()
                    blood = str(
                        row.get('Blood Type') or row.get('Bloodtype')
                        or row.get('BloodType') or row.get('blood_type') or ''
                    ).strip().upper().replace(' ', '')
                    age = _age_group(
                        row.get('AgeYears') or row.get('Age') or row.get('age')
                    )
                    purok = str(
                        row.get('(Current Address) Sitio / Purok / Street Name')
                        or row.get('Purok') or row.get('purok') or ''
                    ).strip()

                    area = counters[barangay]
                    area['records'] += 1
                    overall['records'] += 1
                    if sex and sex not in {'N/A', 'Unknown'}:
                        area['sex'][sex] += 1
                        overall['sex'][sex] += 1
                    if blood in {'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'}:
                        area['blood'][blood] += 1
                        overall['blood'][blood] += 1
                    if age:
                        area['age'][age] += 1
                        overall['age'][age] += 1
                    if purok and purok.lower() not in {'n/a', 'not specified', 'unknown'}:
                        area['purok'][purok] += 1
                        overall['purok'][purok] += 1
        except (OSError, csv.Error):
            continue

    def summarize(values: dict) -> dict:
        return {
            'historical_records': values['records'],
            'common_blood_type': _most_common(values['blood']),
            'common_sex': _most_common(values['sex']),
            'common_age_group': _most_common(values['age']),
            'common_purok': _most_common(values['purok']),
        }

    return ({name: summarize(values) for name, values in counters.items()},
            summarize(overall))


def planning_recommendation(risk_level: str) -> str:
    recommendations = {
        'Critical': 'Immediate CHO coordination and intensified field validation.',
        'High': 'Prioritize validation, source reduction, and resource planning.',
        'Moderate': 'Increase monitoring and reinforce community prevention.',
        'Low': 'Continue routine surveillance and prevention reminders.',
    }
    return recommendations.get(risk_level, 'Continue routine monitoring.')


def classify_risk(predicted_cases: float) -> str:
    """Thresholds shared with the DengueWatch hotspot map."""
    if predicted_cases >= 101:
        return 'Critical'
    if predicted_cases >= 51:
        return 'High'
    if predicted_cases >= 6:
        return 'Moderate'
    return 'Low'


def _weather_description(code: object, rain_mm: float) -> str:
    """Return a simple weather description from Open-Meteo WMO codes."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = -1

    descriptions = {
        0: 'Clear sky',
        1: 'Mainly clear',
        2: 'Partly cloudy',
        3: 'Overcast',
        45: 'Fog',
        48: 'Depositing rime fog',
        51: 'Light drizzle',
        53: 'Moderate drizzle',
        55: 'Dense drizzle',
        56: 'Freezing drizzle',
        57: 'Dense freezing drizzle',
        61: 'Slight rain',
        63: 'Moderate rain',
        65: 'Heavy rain',
        66: 'Freezing rain',
        67: 'Heavy freezing rain',
        71: 'Slight snow',
        73: 'Moderate snow',
        75: 'Heavy snow',
        77: 'Snow grains',
        80: 'Slight rain showers',
        81: 'Moderate rain showers',
        82: 'Violent rain showers',
        85: 'Slight snow showers',
        86: 'Heavy snow showers',
        95: 'Thunderstorm',
        96: 'Thunderstorm with slight hail',
        99: 'Thunderstorm with heavy hail',
    }
    description = descriptions.get(code, 'Weather data available')
    if rain_mm > 0 and code in {0, 1, 2, 3}:
        description = 'Rainfall recorded/forecast'
    return description


def _weather_effect(rain_mm: float, recent_rain_mm: float) -> tuple[str, str]:
    """Explain rainfall as a surveillance signal, not an immediate case forecast."""
    if rain_mm > 0 or recent_rain_mm > 0:
        return (
            'Rainfall signal',
            'Rainfall can create conditions favorable to mosquito breeding. '
            'Dengue cases are not expected to increase immediately from one rainy day; '
            'monitor the following days and weeks, especially if rainfall continues.',
        )
    return (
        'No rainfall signal',
        'No measurable rainfall is shown for the selected day. Continue routine '
        'dengue surveillance and prevention activities.',
    )


def fetch_live_weather(selected_date: date | None = None) -> dict:
    """Fetch weather for a selected Iligan City date plus a short surrounding window.

    Open-Meteo supports recent archived forecast days as well as upcoming forecast
    days. The selected day is used for the weather display and interpretation.
    The Random Forest forecast itself remains a monthly dengue forecast and is not
    changed by a single day's rainfall.
    """
    selected_date = selected_date or datetime.now(ZoneInfo('Asia/Manila')).date()
    today = datetime.now(ZoneInfo('Asia/Manila')).date()
    cache_key = f'iligan_weather_window_{selected_date.isoformat()}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    days_from_today = (selected_date - today).days
    if -7 <= days_from_today <= 7:
        params = {
            'latitude': 8.2280,
            'longitude': 124.2452,
            'daily': (
                'weather_code,temperature_2m_mean,precipitation_sum,'
                'rain_sum,precipitation_hours,relative_humidity_2m_mean'
            ),
            'timezone': 'Asia/Manila',
            'past_days': 7,
            'forecast_days': 7,
        }
        source = 'Open-Meteo weather forecast/archive'
        source_url = 'https://open-meteo.com/en/docs'
    else:
        # For an older requested date, use Open-Meteo's historical weather API.
        params = {
            'latitude': 8.2280,
            'longitude': 124.2452,
            'start_date': selected_date.isoformat(),
            'end_date': selected_date.isoformat(),
            'daily': (
                'weather_code,temperature_2m_mean,precipitation_sum,'
                'rain_sum,precipitation_hours,relative_humidity_2m_mean'
            ),
            'timezone': 'Asia/Manila',
        }
        source = 'Open-Meteo Historical Weather API'
        source_url = 'https://open-meteo.com/en/docs/historical-weather-api'

    base_url = (
        'https://api.open-meteo.com/v1/forecast'
        if -7 <= days_from_today <= 7
        else 'https://archive-api.open-meteo.com/v1/archive'
    )
    url = base_url + '?' + urlencode(params)

    with urlopen(url, timeout=20) as response:
        payload = json.load(response)

    daily = payload.get('daily', {})
    dates = daily.get('time', [])
    if not dates:
        raise ValueError('Weather API returned no daily weather records.')

    def value_at(key: str, target: str, default: float = 0.0):
        values = daily.get(key, [])
        try:
            index = dates.index(target)
            value = values[index]
            return default if value is None else value
        except (ValueError, IndexError, TypeError):
            return default

    selected_iso = selected_date.isoformat()
    rainfall = float(value_at('rain_sum', selected_iso, 0.0))
    precipitation = float(value_at('precipitation_sum', selected_iso, rainfall))
    temperature = float(value_at('temperature_2m_mean', selected_iso, 0.0))
    humidity = float(value_at('relative_humidity_2m_mean', selected_iso, 0.0))
    hours = float(value_at('precipitation_hours', selected_iso, 0.0))
    code = value_at('weather_code', selected_iso, -1)

    recent_rain = 0.0
    for d, value in zip(dates, daily.get('rain_sum', [])):
        if value is None:
            continue
        try:
            if selected_date - timedelta(days=6) <= date.fromisoformat(d) <= selected_date:
                recent_rain += float(value)
        except ValueError:
            continue

    label, effect = _weather_effect(rainfall, recent_rain)
    selected_is_today = selected_date == today

    result = {
        'selected_date': selected_iso,
        'selected_date_label': selected_date.strftime('%B %d, %Y'),
        'relative_label': 'Today' if selected_is_today else (
            'Yesterday' if selected_date == today - timedelta(days=1)
            else selected_date.strftime('%b %d')
        ),
        'weather_description': _weather_description(code, rainfall),
        'weather_code': code,
        'rainfall_mm': round(rainfall, 1),
        'precipitation_mm': round(precipitation, 1),
        'precipitation_hours': round(hours, 1),
        'temperature_c': round(temperature, 1),
        'humidity_pct': round(humidity, 1),
        'recent_7_day_rainfall_mm': round(recent_rain, 1),
        'weather_signal': label,
        'weather_effect': effect,
        'source': source,
        'source_url': source_url,
        'retrieved_at': datetime.now(ZoneInfo('Asia/Manila')).strftime('%B %d, %Y %I:%M %p'),
        'live': True,
    }
    cache.set(cache_key, result, 1800)
    return result


def weather_date_options() -> list[dict]:
    """Return a compact date selector covering recent and upcoming weather."""
    today = datetime.now(ZoneInfo('Asia/Manila')).date()
    options = []
    for offset in range(-7, 8):
        selected = today + timedelta(days=offset)
        if offset == 0:
            label = f'Today — {selected.strftime("%b %d, %Y")}'
        elif offset == -1:
            label = f'Yesterday — {selected.strftime("%b %d, %Y")}'
        elif offset == 1:
            label = f'Tomorrow — {selected.strftime("%b %d, %Y")}'
        else:
            label = selected.strftime('%b %d, %Y')
        options.append({'value': selected.isoformat(), 'label': label})
    return options


def prediction_context(request=None) -> dict:
    """Build the shared prediction page context for CHO and LGU.

    The model is loaded only when the prediction page is requested.  Older
    saved scikit-learn pipelines can fail during unpickling after a version
    change (for example, the private ``_RemainderColsList`` error).  That
    condition is handled here so the Django page shows a useful message
    instead of returning HTTP 500.
    """

    model_path = Path(settings.ML_MODEL_PATH)
    dataset_path = Path(settings.BASE_DIR) / 'datasets' / 'integrated_monthly.csv'

    context = {
        'model_ready': False,
        'forecasts': [],
        'model_metrics': {},
        'high_count': 0,
        'critical_count': 0,
        'moderate_count': 0,
        'low_count': 0,
        'forecast_period': 'Unavailable',
        'case_data_period': 'Unavailable',
        'prediction_error': '',
        'weather': {},
        'demographic_summary': {},
    }

    if not model_path.exists():
        context['prediction_error'] = (
            'The Random Forest model file is missing. '
            'Retrain the model using the current project environment.'
        )
        return context

    if not dataset_path.exists():
        context['prediction_error'] = (
            'The integrated monthly dataset is missing. '
            'Build datasets/integrated_monthly.csv before generating predictions.'
        )
        return context

    # ---------------------------------------------------------
    # LOAD MODEL SAFELY
    # ---------------------------------------------------------
    try:
        artifact = joblib.load(model_path)
    except (
        AttributeError,
        ImportError,
        ModuleNotFoundError,
        ValueError,
        OSError,
    ) as exc:
        error_text = str(exc)

        if '_RemainderColsList' in error_text:
            context['prediction_error'] = (
                'The saved Random Forest model was created with a different '
                'scikit-learn version and cannot be loaded safely. '
                'The current project uses scikit-learn 1.9.0. '
                'Retrain the model with the current environment, then reload this page.'
            )
        else:
            context['prediction_error'] = (
                'The saved Random Forest model could not be loaded safely. '
                f'Details: {error_text}'
            )
        return context

    try:
        data = pd.read_csv(dataset_path)
        profiles, demographic_summary = load_demographic_profiles(dataset_path.parent)

        required_columns = {
            'year', 'month', 'case_count', 'barangay',
            'rainfall_mm', 'temperature_c', 'humidity_pct',
        }
        missing_columns = sorted(required_columns - set(data.columns))
        if missing_columns:
            raise ValueError(
                f"Integrated dataset is missing: {', '.join(missing_columns)}"
            )

        latest_year = int(data['year'].max())
        latest_month = int(
            data.loc[data['year'] == latest_year, 'month'].max()
        )

        engineered = engineer_features(
            data,
            include_target=False,
        )

        latest = engineered[
            (engineered['year'] == latest_year)
            & (engineered['month'] == latest_month)
        ].copy()

        if latest.empty:
            raise ValueError(
                'No rows are available for the latest dataset month.'
            )

        # -----------------------------------------------------
        # WEATHER INPUT / WEATHER DATE CONTEXT
        # -----------------------------------------------------
        selected_weather_date = datetime.now(ZoneInfo('Asia/Manila')).date()
        if request is not None:
            raw_weather_date = str(request.GET.get('weather_date', '')).strip()
            if raw_weather_date:
                try:
                    selected_weather_date = date.fromisoformat(raw_weather_date)
                except ValueError:
                    selected_weather_date = datetime.now(ZoneInfo('Asia/Manila')).date()

        try:
            weather = fetch_live_weather(selected_weather_date)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            ZeroDivisionError,
        ) as exc:
            weather = {
                'selected_date': selected_weather_date.isoformat(),
                'selected_date_label': selected_weather_date.strftime('%B %d, %Y'),
                'relative_label': selected_weather_date.strftime('%b %d'),
                'weather_description': 'Weather data unavailable',
                'weather_code': -1,
                'temperature_c': round(float(latest['temperature_c'].iloc[0]), 1),
                'rainfall_mm': round(float(latest['rainfall_mm'].iloc[0]), 1),
                'precipitation_mm': round(float(latest['rainfall_mm'].iloc[0]), 1),
                'precipitation_hours': 0,
                'humidity_pct': round(float(latest['humidity_pct'].iloc[0]), 1),
                'recent_7_day_rainfall_mm': round(float(latest['rainfall_mm'].iloc[0]), 1),
                'weather_signal': 'Weather unavailable',
                'weather_effect': 'Use the stored weather data and continue routine surveillance.',
                'source': 'Latest stored historical weather',
                'source_url': '',
                'retrieved_at': '',
                'live': False,
                'error': str(exc),
            }

        # The model predicts the next monthly case count. A single rainy day
        # must not be substituted for the model's monthly rainfall feature.
        # The selected weather day is therefore displayed as an explanatory
        # surveillance signal rather than falsely changing the RF prediction.
        input_year = latest_year
        input_month = latest_month

        # -----------------------------------------------------
        # MODEL FEATURES
        # -----------------------------------------------------
        features = artifact.get(
            'metrics',
        ).get(
            'features',
            FEATURES,
        )

        missing_features = [
            field
            for field in features
            if field not in latest.columns
        ]

        if missing_features:
            raise ValueError(
                'Dataset is missing model features: '
                + ', '.join(missing_features)
            )

        pipeline = artifact.get('pipeline')
        if pipeline is None:
            raise ValueError(
                'The saved model artifact does not contain a prediction pipeline.'
            )

        values = pipeline.predict(
            latest[features]
        )

        forecasts = []

        for (_, row), raw_value in zip(
            latest.iterrows(),
            values,
        ):
            predicted = max(
                0,
                round(float(raw_value), 2),
            )

            current = int(
                row['case_count']
            )

            change = round(
                predicted - current,
                2,
            )

            if change > 0.49:
                trend = 'Increasing'
                trend_class = 'trend-up'
            elif change < -0.49:
                trend = 'Decreasing'
                trend_class = 'trend-down'
            else:
                trend = 'Stable'
                trend_class = 'trend-stable'

            if change > 0:
                case_change_display = f'+{change:.2f}'
            else:
                case_change_display = f'{change:.2f}'

            profile = profiles.get(
                str(row['barangay']),
                {},
            )

            risk_level = classify_risk(
                predicted
            )
            blood_shares = {
                blood_type: float(row.get(column, 0) or 0)
                for blood_type, column in zip(BLOOD_TYPES, BLOOD_TYPE_COLUMNS)
            }
            training_blood_type = max(blood_shares, key=blood_shares.get)

            forecasts.append({
                'barangay': row['barangay'],
                'predicted_cases': predicted,
                'risk_level': risk_level,
                'current_cases': current,
                'case_change': change,
                'case_change_display': case_change_display,
                'trend': trend,
                'trend_class': trend_class,
                'rainfall_mm': round(
                    float(row['rainfall_mm']),
                    1,
                ),
                'temperature_c': round(
                    float(row['temperature_c']),
                    1,
                ),
                'humidity_pct': round(
                    float(row['humidity_pct']),
                    1,
                ),
                'common_blood_type': profile.get(
                    'common_blood_type',
                    'Not available',
                ),
                'common_sex': profile.get(
                    'common_sex',
                    'Not available',
                ),
                'common_age_group': profile.get(
                    'common_age_group',
                    'Not available',
                ),
                'common_purok': profile.get(
                    'common_purok',
                    'Not available',
                ),
                'historical_records': profile.get(
                    'historical_records',
                    0,
                ),
                'training_blood_type': training_blood_type if blood_shares[training_blood_type] else 'Not available',
                'training_blood_type_share': round(blood_shares[training_blood_type] * 100, 1),
                'recommendation': planning_recommendation(
                    risk_level
                ),
            })

        forecasts.sort(
            key=lambda item: item['predicted_cases'],
            reverse=True,
        )

        next_month = (
            1
            if input_month == 12
            else input_month + 1
        )

        next_year = (
            input_year + 1
            if input_month == 12
            else input_year
        )

        context.update({
            'model_ready': True,
            'forecasts': forecasts,
            'model_metrics': artifact.get(
                'metrics',
                {},
            ),
            'high_count': sum(
                row['risk_level'] == 'High'
                for row in forecasts
            ),
            'critical_count': sum(
                row['risk_level'] == 'Critical'
                for row in forecasts
            ),
            'moderate_count': sum(
                row['risk_level'] == 'Moderate'
                for row in forecasts
            ),
            'low_count': sum(
                row['risk_level'] == 'Low'
                for row in forecasts
            ),
            'forecast_period': (
                f'{month_name[next_month]} {next_year}'
            ),
            'case_data_period': (
                f'{month_name[latest_month]} {latest_year}'
            ),
            'weather': weather,
            'weather_date_options': weather_date_options(),
            'demographic_summary': demographic_summary,
        })

    except (
        AttributeError,
        ImportError,
        ModuleNotFoundError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        error_text = str(exc)

        if '_RemainderColsList' in error_text:
            context['prediction_error'] = (
                'The saved Random Forest model is incompatible with the '
                'installed scikit-learn version. Retrain the model using '
                'the current environment, then reload this page.'
            )
        else:
            context['prediction_error'] = (
                f'Prediction could not be generated: {error_text}'
            )

    return context
