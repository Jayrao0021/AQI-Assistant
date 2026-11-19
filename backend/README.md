# AQI Assistant — Indian AQI backend, Step 2

Replace `AQI_Project/backend/main.py` with this file. Keep your existing `requirements.txt`.

The existing `uvicorn --reload` terminal should automatically reload. Otherwise restart with:

```
py -m uvicorn main:app --reload --port 8000
```

Open http://127.0.0.1:8000/api/air-quality and check `indian_aqi`, `indian_aqi_category`, `averaged_pollutants`, and `sub_indices`.

The API calculates an *indicative* Indian AQI using CPCB breakpoint bands and 24-hour / 8-hour averaging of Open-Meteo modeled hourly pollutant estimates. It is **not an official CPCB station AQI**. Current pollutant readings and the averaging-window concentrations are different fields. AQI is null when insufficient data is available. The model does not supply NH3 or Pb, so their contribution is not assessed.
