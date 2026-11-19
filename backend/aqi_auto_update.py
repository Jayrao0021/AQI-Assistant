"""Incrementally collect completed daily AQI estimates and optionally retrain models.
Run from the backend directory: py aqi_auto_update.py [--train]
"""
import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from multicity_pipeline import DB, collect, initialize, train


def india_today():
    try:
        return datetime.now(ZoneInfo('Asia/Kolkata')).date()
    except ZoneInfoNotFoundError:
        # Windows Python installations may lack the IANA timezone database.
        from datetime import timezone
        return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


def update(retrain=False):
    end = india_today() - timedelta(days=1)
    if not Path(DB).exists():
        raise SystemExit('Missing multicity_aqi.sqlite3. Collect initial history first.')
    with sqlite3.connect(DB) as conn:
        initialize(conn)
        rows = conn.execute('SELECT city, MAX(date) FROM daily_aqi GROUP BY city').fetchall()
    if not rows:
        raise SystemExit('Dataset is empty. Collect initial history first.')
    # Refresh a few recent days in case the provider revised its estimates.
    start = min(datetime.strptime(last, '%Y-%m-%d').date() for _, last in rows) - timedelta(days=3)
    if start <= end:
        print(f'Collecting updates from {start} through {end}', flush=True)
        collect(start, end)
    else:
        print(f'Already current through {end}', flush=True)
    if retrain:
        print('Retraining models...', flush=True)
        train()
    print('Update complete.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', action='store_true', help='Also retrain the models after collection')
    args = parser.parse_args()
    update(args.train)
