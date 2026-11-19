from datetime import datetime, timedelta, date
from pathlib import Path
import math
import joblib
import pandas as pd
from statistics import mean

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AQI Assistant API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
POLLUTANTS = ("pm2_5", "pm10", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone")

# CPCB breakpoint concentration ranges, in ug/m3 except CO (mg/m3).
# Each tuple is (concentration lower, concentration upper).
BREAKPOINTS = {
    "pm2_5": [(0, 30), (31, 60), (61, 90), (91, 120), (121, 250), (251, 500)],
    "pm10": [(0, 50), (51, 100), (101, 250), (251, 350), (351, 430), (431, 600)],
    "nitrogen_dioxide": [(0, 40), (41, 80), (81, 180), (181, 280), (281, 400), (401, 600)],
    "sulphur_dioxide": [(0, 40), (41, 80), (81, 380), (381, 800), (801, 1600), (1601, 2000)],
    "carbon_monoxide": [(0, 1.0), (1.1, 2.0), (2.1, 10.0), (10.1, 17.0), (17.1, 34.0), (34.1, 50.0)],
    "ozone": [(0, 50), (51, 100), (101, 168), (169, 208), (209, 748), (749, 1000)],
}
AQI_BANDS = [(0, 50, "Good"), (51, 100, "Satisfactory"), (101, 200, "Moderate"),
             (201, 300, "Poor"), (301, 400, "Very Poor"), (401, 500, "Severe")]


def sub_index(name, concentration):
    if concentration is None or concentration < 0:
        return None
    ranges = BREAKPOINTS[name]
    aqi_ranges = [(0, 50), (51, 100), (101, 200), (201, 300), (301, 400), (401, 500)]
    for i, ((low, high), (aqi_low, aqi_high)) in enumerate(zip(ranges, aqi_ranges)):
        if concentration <= high:
            # Round to the nearest reporting precision before comparing ranges.
            # If it falls between adjacent tabulated bounds, use the next band.
            concentration = max(low, concentration)
            return round(aqi_low + (concentration - low) * (aqi_high - aqi_low) / (high - low))
    return 500


def category(aqi):
    return next(label for low, high, label in AQI_BANDS if aqi <= high)


def recent_average(hourly, key, end_time, hours):
    times = hourly.get("time", [])
    values = hourly.get(key, [])
    start_time = end_time - timedelta(hours=hours - 1)
    samples = []
    for time_string, value in zip(times, values):
        timestamp = datetime.fromisoformat(time_string)
        if start_time <= timestamp <= end_time and value is not None:
            samples.append(float(value))
    # Require at least 75% of expected hourly observations.
    if len(samples) < (hours * 3 + 3) // 4:
        return None
    return round(mean(samples), 2)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AQI Assistant API"}


@app.get("/api/locations")
async def locations(query: str = Query(min_length=2, max_length=100)):
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(GEOCODING_URL, params={
                "name": query, "count": 8, "language": "en", "format": "json"
            })
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Location service unavailable") from exc
    return [{"name": item["name"], "country": item.get("country", ""),
             "admin1": item.get("admin1", ""), "latitude": item["latitude"],
             "longitude": item["longitude"]} for item in data.get("results", [])]


@app.get("/api/air-quality")
async def air_quality(
    latitude: float = Query(28.6139, ge=-90, le=90),
    longitude: float = Query(77.2090, ge=-180, le=180),
):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(AIR_QUALITY_URL, params={
                "latitude": latitude, "longitude": longitude,
                "current": ",".join(POLLUTANTS),
                "hourly": ",".join(POLLUTANTS),
                "past_days": 2, "forecast_days": 1, "timezone": "auto",
            })
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Air-quality provider unavailable") from exc

    current = data.get("current")
    hourly = data.get("hourly")
    if not current or not hourly or not current.get("time"):
        raise HTTPException(status_code=502, detail="Incomplete air-quality data returned")

    # The current timestamp can represent a partial hour; use the last completed
    # hourly timestamp to avoid including future or incomplete hourly values.
    current_time = datetime.fromisoformat(current["time"])
    eligible_times = [datetime.fromisoformat(t) for t in hourly.get("time", [])
                      if datetime.fromisoformat(t) < current_time]
    if not eligible_times:
        raise HTTPException(status_code=502, detail="No completed hourly observations")
    end_time = max(eligible_times)

    averages = {}
    sub_indices = {}
    for key in POLLUTANTS:
        hours = 8 if key in ("carbon_monoxide", "ozone") else 24
        avg = recent_average(hourly, key, end_time, hours)
        if key == "carbon_monoxide" and avg is not None:
            avg = round(avg / 1000, 3)  # Open-Meteo ug/m3 -> CPCB mg/m3
        averages[key] = avg
        sub_indices[key] = sub_index(key, avg)

    available = {k: v for k, v in sub_indices.items() if v is not None}
    valid = len(available) >= 3 and any(k in available for k in ("pm2_5", "pm10"))
    indian_aqi = max(available.values()) if valid else None
    dominant = max(available, key=available.get) if valid else None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "observed_at": current.get("time"),
        "averages_ending_at": end_time.isoformat(timespec="minutes"),
        "timezone": data.get("timezone"),
        "pollutants": {key: current.get(key) for key in POLLUTANTS},
        "units": data.get("current_units", {}),
        "averaged_pollutants": averages,
        "averaged_units": {k: ("mg/m3" if k == "carbon_monoxide" else "ug/m3") for k in POLLUTANTS},
        "sub_indices": sub_indices,
        "indian_aqi": indian_aqi,
        "indian_aqi_category": category(indian_aqi) if indian_aqi is not None else None,
        "dominant_pollutant": dominant,
        "indian_aqi_status": "estimated_from_modeled_concentrations" if valid else "insufficient_data",
        "source": "Open-Meteo Air Quality API (modeled estimates, NOT official CPCB station AQI)",
        "note": "Indicative CPCB-style AQI from modeled hourly concentrations. Not an official CPCB measurement."
    }


@app.get("/api/history")
async def history(
    latitude: float = Query(28.6139, ge=-90, le=90),
    longitude: float = Query(77.2090, ge=-180, le=180),
    days: int = Query(7, ge=7, le=30),
):
    # Fetch complete calendar days only; today's data is still incomplete.
    # The provider interprets dates in the requested local timezone.
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(AIR_QUALITY_URL, params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(POLLUTANTS),
                "past_days": 32,
                "forecast_days": 1,
                "timezone": "auto",
            })
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Historical air-quality provider unavailable") from exc

    hourly = data.get("hourly") or {}
    timestamps = hourly.get("time") or []
    if not timestamps:
        raise HTTPException(status_code=502, detail="No historical hourly data returned")

    # Open-Meteo hourly timestamps are local clock times when timezone=auto.
    # The current local date is provided by the API's current field if requested;
    # use UTC offset returned by the API to identify today for the location.
    offset = timedelta(seconds=data.get("utc_offset_seconds", 0))
    today = (datetime.utcnow() + offset).date()
    first_day = today - timedelta(days=days)
    results = []
    for n in range(days):
        day = first_day + timedelta(days=n)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(hours=23)
        averages = {}
        sub_indices = {}
        for pollutant in POLLUTANTS:
            # 24h calendar-day averages for PM and gases requiring 24h.
            # For CO and O3, use the highest valid rolling 8h average
            # whose window ends within the selected calendar day.
            if pollutant in ("carbon_monoxide", "ozone"):
                candidates = []
                for hour in range(7, 24):
                    avg = recent_average(hourly, pollutant, day_start + timedelta(hours=hour), 8)
                    if avg is not None:
                        candidates.append(avg)
                avg = max(candidates) if candidates else None
            else:
                avg = recent_average(hourly, pollutant, day_end, 24)
            if pollutant == "carbon_monoxide" and avg is not None:
                avg = round(avg / 1000, 3)
            averages[pollutant] = avg
            sub_indices[pollutant] = sub_index(pollutant, avg)
        available = {k: v for k, v in sub_indices.items() if v is not None}
        valid = len(available) >= 3 and ("pm2_5" in available or "pm10" in available)
        value = max(available.values()) if valid else None
        results.append({
            "date": day.isoformat(),
            "aqi": value,
            "category": category(value) if value is not None else None,
            "dominant_pollutant": max(available, key=available.get) if valid else None,
        })

    return {
        "latitude": latitude,
        "longitude": longitude,
        "days": days,
        "timezone": data.get("timezone"),
        "history": results,
        "source": "Open-Meteo modeled pollutant concentrations",
        "method": "Indicative CPCB-style daily AQI: 24h means, maximum completed-day rolling 8h means for CO/O3; excludes NH3 and Pb",
        "note": "Historical modeled estimates, not official CPCB monitoring-station readings. Some dates may be unavailable.",
    }


MODEL_PATH = Path(__file__).resolve().parent / "Indian_AQI_Models.pkl"

@app.get("/api/forecast")
async def forecast(
    latitude: float = Query(28.6139, ge=-90, le=90),
    longitude: float = Query(77.2090, ge=-180, le=180),
):
    # The trained models are specific to Delhi. Do not apply to other cities.
    if abs(latitude - 28.6139) > 0.15 or abs(longitude - 77.2090) > 0.15:
        raise HTTPException(status_code=422, detail="Experimental ML forecasts are currently available only for Delhi.")
    if not MODEL_PATH.exists():
        raise HTTPException(status_code=503, detail="Indian_AQI_Models.pkl is missing from the backend folder.")
    try:
        # Only load model files you trust. Never accept a model path from a request.
        artifact = joblib.load(MODEL_PATH)
        expected = ['AQI','Month','Day','DayOfWeek','AQI_Lag1','AQI_Lag3','AQI_Lag7','AQI_Rolling3','AQI_Rolling7']
        if artifact.get('features') != expected or artifact.get('city') != 'Delhi':
            raise ValueError('Incompatible model artifact')
    except Exception as exc:
        print("MODEL LOADING ERROR:", repr(exc), flush=True)
        raise HTTPException(
            status_code=503,
            detail=f"Model loading failed: {type(exc).__name__}: {exc}"
        ) from exc    

    # Reuse the same daily CPCB-style historical estimates as the chart.
    result = await history(latitude=latitude, longitude=longitude, days=30)
    rows = result['history']
    values = {row['date']: row['aqi'] for row in rows if isinstance(row.get('aqi'), (int,float))}
    if not rows:
        raise HTTPException(status_code=503, detail="No recent AQI history is available.")
    anchor = date.fromisoformat(rows[-1]['date'])
    needed = [anchor - timedelta(days=n) for n in range(8)]
    if any(d.isoformat() not in values for d in needed):
        raise HTTPException(status_code=503, detail="Insufficient consecutive historical daily AQI estimates for forecast features.")
    def aqi_at(n):
        return float(values[(anchor - timedelta(days=n)).isoformat()])
    features = pd.DataFrame([{
        'AQI': aqi_at(0), 'Month': anchor.month, 'Day': anchor.day,
        'DayOfWeek': anchor.weekday(), 'AQI_Lag1': aqi_at(1),
        'AQI_Lag3': aqi_at(3), 'AQI_Lag7': aqi_at(7),
        'AQI_Rolling3': sum(aqi_at(n) for n in range(1,4))/3,
        'AQI_Rolling7': sum(aqi_at(n) for n in range(1,8))/7,
    }], columns=expected)
    predictions = []
    for horizon in (1,3,7):
        model = artifact['models'].get(horizon)
        if model is None:
            raise HTTPException(status_code=503, detail=f"Model for {horizon}-day forecast is unavailable.")
        predicted = float(model.predict(features)[0])
        if not math.isfinite(predicted):
            raise HTTPException(status_code=503, detail="Model returned an invalid prediction.")
        predicted = round(max(0, min(500, predicted)))
        predictions.append({
            'horizon_days': horizon,
            'date': (anchor + timedelta(days=horizon)).isoformat(),
            'aqi': predicted,
            'category': category(predicted),
        })
    return {
        'location': 'Delhi, India', 'aqi_type': 'Indian AQI',
        'as_of': anchor.isoformat(), 'predictions': predictions,
        'status': 'experimental_unvalidated_recent_data',
        'training_last_date': artifact.get('last_training_date'),
        'source': 'Delhi historical city_day.csv models applied to Open-Meteo modeled CPCB-style estimates',
        'warning': 'Research demonstration only. Training data ends in 2020 and model performance has not been validated on recent Open-Meteo data. Do not use for health or safety decisions.',
    }
