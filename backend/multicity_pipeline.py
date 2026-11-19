"""Multi-city modeled Indian AQI research pipeline. Run from backend folder."""
import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from main import POLLUTANTS, recent_average, sub_index

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'multicity_aqi.sqlite3'
MODEL = ROOT / 'Multicity_AQI_Models.pkl'
API = 'https://air-quality-api.open-meteo.com/v1/air-quality'
CITIES = {
    'Delhi': (28.6139, 77.2090),
    'Ahmedabad': (23.0225, 72.5714),
    'Mumbai': (19.0760, 72.8777),
    'Bengaluru': (12.9716, 77.5946),
    'Kolkata': (22.5726, 88.3639),
}
HORIZONS = (1, 3, 7)
BASE_FEATURES = ['AQI', 'Month', 'Day', 'DayOfWeek', 'AQI_Lag1', 'AQI_Lag3', 'AQI_Lag7', 'AQI_Rolling3', 'AQI_Rolling7']


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS daily_aqi (
        city TEXT NOT NULL, date TEXT NOT NULL, aqi INTEGER NOT NULL,
        source TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(city, date))''')
    conn.commit()


def compute_daily(hourly, day):
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(hours=23)
    indices = {}
    for pollutant in POLLUTANTS:
        if pollutant in ('carbon_monoxide', 'ozone'):
            candidates = [recent_average(hourly, pollutant, start + timedelta(hours=h), 8)
                          for h in range(7, 24)]
            candidates = [v for v in candidates if v is not None]
            avg = max(candidates) if candidates else None
        else:
            avg = recent_average(hourly, pollutant, end, 24)
        if pollutant == 'carbon_monoxide' and avg is not None:
            avg /= 1000
        indices[pollutant] = sub_index(pollutant, avg)
    valid = {k: v for k, v in indices.items() if v is not None}
    if len(valid) < 3 or not ({'pm2_5', 'pm10'} & valid.keys()):
        return None
    return int(max(valid.values()))


def collect(start_date, end_date):
    if start_date > end_date:
        raise ValueError('Start date must be on or before end date')
    if end_date >= date.today():
        raise ValueError('Collect completed past days only; end date must be before today')
    with sqlite3.connect(DB) as conn, httpx.Client(timeout=90) as client:
        initialize(conn)
        for city, (lat, lon) in CITIES.items():
            total = 0
            # Chunk requests to limit payload size. A one-day overlap is not required:
            # 8h windows are evaluated within each calendar day.
            cursor = start_date
            while cursor <= end_date:
                chunk_end = min(end_date, cursor + timedelta(days=89))
                print(f'Fetching {city}: {cursor} to {chunk_end}', flush=True)
                resp = client.get(API, params={
                    'latitude': lat, 'longitude': lon, 'timezone': 'Asia/Kolkata',
                    'start_date': cursor.isoformat(), 'end_date': chunk_end.isoformat(),
                    'hourly': ','.join(POLLUTANTS),
                })
                resp.raise_for_status()
                hourly = resp.json().get('hourly') or {}
                if not hourly.get('time'):
                    raise RuntimeError(f'No hourly data returned for {city} {cursor}')
                day = cursor
                rows = []
                while day <= chunk_end:
                    aqi = compute_daily(hourly, day)
                    if aqi is not None:
                        rows.append((city, day.isoformat(), aqi,
                                     'Open-Meteo modeled CPCB-style estimate', datetime.utcnow().isoformat()))
                    day += timedelta(days=1)
                conn.executemany('''INSERT INTO daily_aqi (city,date,aqi,source,updated_at)
                    VALUES (?,?,?,?,?) ON CONFLICT(city,date) DO UPDATE SET
                    aqi=excluded.aqi,source=excluded.source,updated_at=excluded.updated_at''', rows)
                conn.commit()
                total += len(rows)
                cursor = chunk_end + timedelta(days=1)
            print(f'{city}: stored/updated {total} daily values', flush=True)


def make_features(df):
    frames = []
    for city, group in df.groupby('city'):
        g = group.copy().sort_values('date').set_index('date').asfreq('D')
        g['city'] = city
        g['Month'] = g.index.month
        g['Day'] = g.index.day
        g['DayOfWeek'] = g.index.dayofweek
        g['AQI'] = g['aqi'].astype(float)
        for lag in (1, 3, 7):
            g[f'AQI_Lag{lag}'] = g['AQI'].shift(lag)
            g[f'Target_{lag}Day'] = g['AQI'].shift(-lag)
        for window in (3, 7):
            g[f'AQI_Rolling{window}'] = g['AQI'].shift(1).rolling(window).mean()
        frames.append(g.reset_index().rename(columns={'index': 'date'}))
    result = pd.concat(frames, ignore_index=True)
    for city in CITIES:
        result[f'city_{city}'] = (result['city'] == city).astype(int)
    return result


def train():
    if not DB.exists():
        raise RuntimeError('Dataset missing. Run collect first.')
    with sqlite3.connect(DB) as conn:
        raw = pd.read_sql_query('SELECT city,date,aqi FROM daily_aqi ORDER BY date', conn)
    if raw.empty:
        raise RuntimeError('No training rows in database.')
    raw['date'] = pd.to_datetime(raw['date'])
    data = make_features(raw)
    features = BASE_FEATURES + [f'city_{city}' for city in CITIES]
    models = {}
    report = []
    for horizon in HORIZONS:
        target = f'Target_{horizon}Day'
        valid = data.dropna(subset=features + [target]).copy()
        dates = sorted(valid['date'].unique())
        if len(dates) < 180:
            raise RuntimeError('Need at least 180 complete dates; collect more history.')
        cutoff = dates[int(len(dates) * 0.8)]
        # Prevent leakage: training labels must occur before first test feature date.
        train_rows = valid[valid['date'] + pd.Timedelta(days=horizon) < cutoff]
        test_rows = valid[valid['date'] >= cutoff]
        if len(train_rows) < 100 or len(test_rows) < 30:
            raise RuntimeError('Insufficient train/test observations.')
        candidates = {
            'RandomForest': RandomForestRegressor(n_estimators=120, min_samples_leaf=4, random_state=42, n_jobs=-1),
            'HistGradientBoosting': HistGradientBoostingRegressor(max_iter=150, l2_regularization=5, random_state=42),
        }
        baseline_mae = mean_absolute_error(test_rows[target], test_rows['AQI'])
        best = None
        for name, estimator in candidates.items():
            estimator.fit(train_rows[features], train_rows[target])
            predictions = estimator.predict(test_rows[features])
            mae = mean_absolute_error(test_rows[target], predictions)
            rmse = np.sqrt(mean_squared_error(test_rows[target], predictions))
            report.append({'horizon_days': horizon, 'model': name, 'mae': round(float(mae), 2),
                           'rmse': round(float(rmse), 2), 'baseline_mae': round(float(baseline_mae), 2),
                           'train_end': str(train_rows['date'].max().date()),
                           'test_start': str(test_rows['date'].min().date()),
                           'test_end': str(test_rows['date'].max().date()),
                           'test_rows': len(test_rows)})
            if best is None or mae < best[0]:
                best = (mae, name)
        selected = candidates[best[1]]
        selected.fit(valid[features], valid[target])
        models[horizon] = selected
        print(f'{horizon} day: {best[1]} | test MAE {best[0]:.1f} | persistence baseline {baseline_mae:.1f}')
        if best[0] >= baseline_mae:
            print('WARNING: model did not beat simple persistence baseline on held-out dates.')
    artifact = {'models': models, 'features': features, 'cities': list(CITIES),
                'aqi_type': 'Indicative Indian AQI from Open-Meteo modeled concentrations',
                'last_training_date': str(raw['date'].max().date()),
                'note': 'Experimental research model. Not official CPCB AQI or validated health guidance.'}
    joblib.dump(artifact, MODEL)
    pd.DataFrame(report).to_csv(ROOT / 'Multicity_Model_Results.csv', index=False)
    print('Saved', MODEL.name, 'and Multicity_Model_Results.csv')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['collect', 'train', 'update'])
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default=(date.today() - timedelta(days=1)).isoformat())
    args = parser.parse_args()
    if args.command in ('collect', 'update'):
        start = date.fromisoformat(args.start)
        if args.command == 'update' and DB.exists():
            with sqlite3.connect(DB) as conn:
                initialize(conn)
                latest = conn.execute('SELECT MIN(latest) FROM (SELECT MAX(date) AS latest FROM daily_aqi GROUP BY city)').fetchone()[0]
            if latest:
                start = max(start, date.fromisoformat(latest) - timedelta(days=7))
        collect(start, date.fromisoformat(args.end))
    if args.command in ('train', 'update'):
        train()


if __name__ == '__main__':
    main()
