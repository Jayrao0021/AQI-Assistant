import traceback
from datetime import datetime, timedelta, date
from pathlib import Path
import math
import os
import asyncio
from datetime import timezone
import joblib
import pandas as pd
from statistics import mean

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AQI Assistant API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "https://aqi-assistant.vercel.app",
        "https://aqi-assistant-w59o.vercel.app",
    ],
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


# OpenAQ uses station measurements, not the Open-Meteo model. The key stays
# on the server: set OPENAQ_API_KEY in the backend environment.
OPENAQ_URL = "https://api.openaq.org/v3"
US_PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150), (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500),
]
US_PM10_BREAKPOINTS = [
    (0, 54, 0, 50), (55, 154, 51, 100),
    (155, 254, 101, 150), (255, 354, 151, 200),
    (355, 424, 201, 300), (425, 604, 301, 500),
]
US_BANDS = [(50, "Good"), (100, "Moderate"), (150, "Unhealthy for Sensitive Groups"),
            (200, "Unhealthy"), (300, "Very Unhealthy"), (500, "Hazardous")]


def us_pm_aqi(pollutant, concentration):
    # US EPA 2024 PM2.5 breakpoints; PM2.5 truncates to 0.1 ug/m3,
    # PM10 truncates to whole ug/m3. Values >500 are capped for display.
    if concentration is None or not math.isfinite(concentration) or concentration < 0:
        return None
    if pollutant == "pm25":
        concentration = math.floor(concentration * 10) / 10
        bands = US_PM25_BREAKPOINTS
    elif pollutant == "pm10":
        concentration = math.floor(concentration)
        bands = US_PM10_BREAKPOINTS
    else:
        return None
    for low, high, aqi_low, aqi_high in bands:
        if concentration <= high:
            concentration = max(low, concentration)
            return round((aqi_high - aqi_low) * (concentration - low) / (high - low) + aqi_low)
    return 500


def us_category(value):
    return next((name for high, name in US_BANDS if value <= high), "Hazardous")


def utc_timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None


async def openaq_station_aqi(latitude, longitude):
    """Return a recent station-based US AQI, or an explicit unavailable status.

    Avoid combining sensors from different stations. For PM, use >=18 valid hourly
    measurements within the last 24 hours and a measurement <=3 hours old.
    This is a provisional PM-based index, not official EPA NowCast/city AQI.
    """
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key:
        return {"status": "not_configured", "detail": "Set OPENAQ_API_KEY on the backend."}
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=27)).isoformat(timespec="seconds").replace("+00:00", "Z")
    headers = {"X-API-Key": key}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            response = await client.get(f"{OPENAQ_URL}/locations", params={
                "coordinates": f"{latitude},{longitude}", "radius": 25000, "limit": 100,
            })
            response.raise_for_status()
            locations = response.json().get("results", [])
            candidates = []
            for loc in locations:
                last = utc_timestamp((loc.get("datetimeLast") or {}).get("utc"))
                if last is None or (now - last).total_seconds() > 3 * 3600:
                    continue
                sensors = {item.get("parameter", {}).get("name"): item.get("id")
                           for item in loc.get("sensors", [])}
                if not (sensors.get("pm25") or sensors.get("pm10")):
                    continue
                provider = (loc.get("provider") or {}).get("name", "Unknown")
                official = "cpcb" in provider.lower() or "cpcb" in (loc.get("name") or "").lower()
                candidates.append((official, loc, sensors))
            # Prefer official stations; then distance. Check a bounded number
            # of candidates to avoid exhausting the free API quota.
            candidates.sort(key=lambda x: (not x[0], x[1].get("distance") or 1e9))
            for official, loc, sensors in candidates[:8]:
                readings = {}
                last_observed = None
                for pollutant in ("pm25", "pm10"):
                    sensor_id = sensors.get(pollutant)
                    if not sensor_id:
                        continue
                    try:
                        r = await client.get(f"{OPENAQ_URL}/sensors/{sensor_id}/measurements",
                                             params={"datetime_from": since, "limit": 100})
                        r.raise_for_status()
                        observations = r.json().get("results", [])
                    except (httpx.HTTPError, ValueError):
                        continue
                    samples = {}
                    for obs in observations:
                        stamp = utc_timestamp(((obs.get("period") or {}).get("datetimeTo") or {}).get("utc"))
                        value = obs.get("value")
                        if stamp is None or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                            continue
                        if now - timedelta(hours=24) <= stamp <= now + timedelta(minutes=5):
                            samples[stamp.replace(minute=0, second=0, microsecond=0)] = float(value)
                    if len(samples) < 18:
                        continue
                    latest = max(samples)
                    if (now - latest).total_seconds() > 3 * 3600:
                        continue
                    avg = sum(samples.values()) / len(samples)
                    readings[pollutant] = {"average_24h": round(avg, 2), "hourly_samples": len(samples),
                                           "us_sub_index": us_pm_aqi(pollutant, avg)}
                    if last_observed is None or latest > last_observed:
                        last_observed = latest
                indices = {name: item["us_sub_index"] for name, item in readings.items()
                           if item["us_sub_index"] is not None}
                if indices:
                    dominant = max(indices, key=indices.get)
                    value = indices[dominant]
                    return {
                        "status": "available", "us_aqi": value,
                        "us_aqi_category": us_category(value), "dominant_pollutant": dominant,
                        "station": loc.get("name"), "station_id": loc.get("id"),
                        "provider": (loc.get("provider") or {}).get("name"),
                        "official_cpcb_station": official,
                        "distance_meters": round(loc.get("distance") or 0),
                        "observed_at": last_observed.isoformat(),
                        "pollutant_averages": readings,
                        "source": "OpenAQ station measurements",
                        "method": "Provisional US EPA PM-based 24-hour index; not official US EPA NowCast or a citywide AQI",
                        "note": "Nearby station, not necessarily representative of the city. Other pollutants are not included.",
                    }
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "provider_unavailable", "detail": type(exc).__name__}
    return {"status": "no_recent_qualified_station", "detail":
            "No nearby station passed the 3-hour freshness and 18-hour coverage checks."}


@app.get("/api/station-air-quality")
async def station_air_quality(
    latitude: float = Query(28.6139, ge=-90, le=90),
    longitude: float = Query(77.2090, ge=-180, le=180),
):
    return await openaq_station_aqi(latitude, longitude)


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


MODEL_PATH = Path(__file__).resolve().parent / "Multicity_AQI_Models.pkl"

CITY_COORDINATES = {
    "Delhi": (28.6139, 77.2090),
    "Ahmedabad": (23.0225, 72.5714),
    "Mumbai": (19.0760, 72.8777),
    "Bengaluru": (12.9716, 77.5946),
    "Kolkata": (22.5726, 88.3639),
}
BASE_FEATURES = ["AQI", "Month", "Day", "DayOfWeek", "AQI_Lag1", "AQI_Lag3", "AQI_Lag7", "AQI_Rolling3", "AQI_Rolling7"]


@app.get("/api/forecast")
async def forecast(
    latitude: float = Query(28.6139, ge=-90, le=90),
    longitude: float = Query(77.2090, ge=-180, le=180),
):
    # These models were trained at specific city-center coordinates.
    # Do not apply them to arbitrary locations or a whole metropolitan region.
    city = next((name for name, (lat, lon) in CITY_COORDINATES.items()
                 if abs(latitude - lat) < 0.03 and abs(longitude - lon) < 0.03), None)
    if city is None:
        raise HTTPException(status_code=422, detail="Experimental forecasts are supported for the five trained city centers only.")
    if not MODEL_PATH.exists():
        raise HTTPException(status_code=503, detail="Multicity_AQI_Models.pkl is missing. Run multicity_pipeline.py train.")

    try:
        # Only load local model artifacts that you created and trust.
        artifact = joblib.load(MODEL_PATH)
        expected = BASE_FEATURES + [f"city_{name}" for name in CITY_COORDINATES]
        if artifact.get("features") != expected or artifact.get("cities") != list(CITY_COORDINATES):
            raise ValueError("Incompatible multi-city model artifact")
    except Exception as exc:
        import traceback
        print("MULTICITY MODEL ERROR:", repr(exc), flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"Model loading failed: {type(exc).__name__}") from exc

    # Fetch recent completed daily estimates for the selected trained city.
    result = await history(latitude=latitude, longitude=longitude, days=30)
    rows = result["history"]
    values = {r["date"]: float(r["aqi"]) for r in rows
              if isinstance(r.get("aqi"), (int, float)) and math.isfinite(r["aqi"])}
    if not rows:
        raise HTTPException(status_code=503, detail="Recent AQI history unavailable.")
    anchor = date.fromisoformat(rows[-1]["date"])
    if any((anchor - timedelta(days=n)).isoformat() not in values for n in range(8)):
        raise HTTPException(status_code=503, detail="Insufficient consecutive daily AQI history.")

    def aqi_at(n):
        return values[(anchor - timedelta(days=n)).isoformat()]

    record = {
        "AQI": aqi_at(0), "Month": anchor.month, "Day": anchor.day,
        "DayOfWeek": anchor.weekday(), "AQI_Lag1": aqi_at(1),
        "AQI_Lag3": aqi_at(3), "AQI_Lag7": aqi_at(7),
        "AQI_Rolling3": sum(aqi_at(n) for n in range(1, 4)) / 3,
        "AQI_Rolling7": sum(aqi_at(n) for n in range(1, 8)) / 7,
    }
    record.update({f"city_{name}": int(city == name) for name in CITY_COORDINATES})
    features = pd.DataFrame([record], columns=expected)
    predictions = []
    for horizon in (1, 3, 7):
        if horizon == 1:
            predicted = aqi_at(0)  # Persistence beat ML on the held-out 1-day test.
            method = "persistence_baseline"
        else:
            model = artifact["models"].get(horizon)
            if model is None:
                raise HTTPException(status_code=503, detail=f"Missing {horizon}-day model.")
            predicted = float(model.predict(features)[0])
            method = "machine_learning"
        if not math.isfinite(predicted):
            raise HTTPException(status_code=503, detail="Invalid forecast result.")
        predicted = round(max(0, min(500, predicted)))
        predictions.append({
            "horizon_days": horizon,
            "date": (anchor + timedelta(days=horizon)).isoformat(),
            "aqi": predicted,
            "category": category(predicted),
            "method": method,
        })

    return {
        "location": f"{city}, India",
        "aqi_type": "Indian AQI (indicative)",
        "as_of": anchor.isoformat(),
        "predictions": predictions,
        "status": "experimental_recent_data",
        "training_last_date": artifact.get("last_training_date"),
        "source": "Open-Meteo modeled concentrations; multi-city 2024–2026 training data",
        "warning": "Research demonstration only. AQI values are modeled CPCB-style estimates, not official CPCB measurements. Forecasts are not suitable for health or safety decisions.",
    }
