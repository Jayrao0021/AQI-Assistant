# AQI Assistant

**AQI Assistant** is a full-stack air-quality dashboard and experimental machine-learning forecasting project. It brings together current air-quality information, historical trends, and 1-, 3-, and 7-day AQI forecasts in a responsive web interface.

> **Academic project disclaimer:** The application combines different data sources and AQI scales. Experimental forecasts are **not** official monitoring-station predictions and should not be used as the sole basis for health decisions.

## Features

- Search for locations and view air-quality information.
- Explore AQI trends and pollutant information.
- View experimental AQI forecasts for **1, 3, and 7 days**.
- Access available nearby station-based observations through OpenAQ.
- Responsive dashboard with charts, AQI categories, and general health guidance.
- Interactive API documentation powered by FastAPI.

## Technology stack

| Layer | Technologies |
| --- | --- |
| Frontend | React, Vite, JavaScript, CSS, Recharts, Lucide icons, Motion |
| Backend | Python, FastAPI |
| Data sources | Open-Meteo (geocoding and modeled air quality), OpenAQ (station observations where available) |
| Forecasting | Experimental machine-learning models loaded by the backend |
| Deployment | Vercel (frontend), Render (backend) |
| Version control | Git and GitHub |

## Forecasting scope

The experimental forecasting component covers five Indian cities:

**Delhi · Ahmedabad · Mumbai · Bengaluru · Kolkata**

Models were trained using historical Open-Meteo-derived air-quality data and produce **1-day, 3-day, and 7-day** forecasts. Their outputs represent modeled AQI estimates, not official station measurements. The project should be evaluated using documented train/test splits and forecasting metrics before making accuracy claims.

### Understanding the AQI readings

- **Modeled Indian AQI:** The dashboard's historical/forecast series is based on modeled pollutant data and Indian AQI categorization.
- **Station-based US AQI:** Where OpenAQ station data is available, the backend can estimate a US AQI value from available particulate-matter observations.
- These values use **different sources and potentially different scales**, so they should not be treated as interchangeable.

## Repository structure

```text
AQI-Assistant/
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── App.css
│   └── package.json
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── Multicity_AQI_Models.pkl
└── README.md
```

The structure above shows the main application files; additional data, configuration, and assets may be present.

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/Jayrao0021/AQI-Assistant.git
cd AQI-Assistant
```

### 2. Start the backend

On Windows PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Backend API: `http://127.0.0.1:8000`  
API documentation: `http://127.0.0.1:8000/docs`

For station-data features, configure the `OPENAQ_API_KEY` environment variable with your own key. **Never commit API keys to GitHub.**

### 3. Start the frontend

Open a **second terminal** in the project directory:

```powershell
cd frontend
npm install
npm run dev
```

Open the local address shown by Vite (typically `http://localhost:5173`).

To connect to a different backend, set `VITE_API_BASE_URL` in the frontend environment, for example:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## API endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Backend health check |
| `GET /api/locations` | Search/geocode locations |
| `GET /api/air-quality` | Modeled air-quality data |
| `GET /api/station-air-quality` | Available station-based air-quality information |
| `GET /api/history` | Historical AQI series |
| `GET /api/forecast` | Experimental forecast results |

Refer to `/docs` for the exact query parameters and response schemas.

## Deployment

- **Frontend:** Vercel, with the project root set to `frontend` and the environment variable `VITE_API_BASE_URL` pointing to the deployed backend.
- **Backend:** Render, with any required backend secrets configured in Render's environment settings.

Backend health endpoint: https://aqi-assistant-api.onrender.com/api/health

*Add the public Vercel website URL here after the frontend deployment succeeds.*

## Limitations and future improvements

- AQI estimates depend on data availability, pollutant coverage, and model quality.
- OpenAQ observations may be unavailable for some locations or times.
- Model accuracy and generalization should be validated and reported explicitly.
- Future work could include more cities, forecast uncertainty ranges, stronger evaluation baselines, and clearer source/scale labeling.

## Project purpose

Developed as an academic project to explore **air-quality data integration, web application development, and machine-learning-based time-series forecasting**.

## Repository

https://github.com/Jayrao0021/AQI-Assistant
