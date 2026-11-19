
import streamlit as st
import pandas as pd
import requests
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="Delhi AQI Intelligence",
    page_icon="🌍",
    layout="wide"
)

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    max-width: 1250px;
}
h1, h2, h3 {
    letter-spacing: -0.5px;
}
[data-testid="stMetric"] {
    background: rgba(120, 140, 170, 0.09);
    padding: 18px;
    border: 1px solid rgba(140, 150, 170, 0.2);
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

MODEL_PATH = Path(__file__).parent / "Live_AQI_Models.pkl"

def get_category(aqi):
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"

@st.cache_resource
def load_models():
    return joblib.load(MODEL_PATH)

@st.cache_data(ttl=1800)
def fetch_data():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    yesterday = today - timedelta(days=1)
    start = yesterday - timedelta(days=30)

    params = {
        "latitude": 28.6139,
        "longitude": 77.2090,
        "start_date": start.isoformat(),
        "end_date": yesterday.isoformat(),
        "hourly": "us_aqi",
        "current": "us_aqi,pm2_5,pm10",
        "timezone": "Asia/Kolkata"
    }

    response = requests.get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        params=params,
        timeout=45
    )
    response.raise_for_status()
    return response.json()

st.title("🌍 Delhi Air Quality Intelligence")
st.caption(
    "Live air-quality estimates and experimental "
    "machine learning forecasts | US AQI scale"
)

if st.button("🔄 Refresh Live Data"):
    fetch_data.clear()
    st.rerun()

try:
    saved = load_models()
    api = fetch_data()
    current = api["current"]

    current_aqi = current.get("us_aqi")
    pm25 = current.get("pm2_5")
    pm10 = current.get("pm10")

    st.subheader("Current Air Quality")

    c1, c2, c3 = st.columns(3)

    c1.metric("US AQI", current_aqi)
    c2.metric("PM2.5 (µg/m³)", pm25)
    c3.metric("PM10 (µg/m³)", pm10)

    if current_aqi is not None:
        st.write(
            "**Air Quality Category:** "
            + get_category(current_aqi)
        )

    st.caption(
        f"API estimate time: {current.get('time')} "
        "(Asia/Kolkata)"
    )

    hourly = pd.DataFrame(api["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"])
    hourly["Date"] = hourly["time"].dt.normalize()

    daily = hourly.groupby("Date").agg(
        AQI=("us_aqi", "mean"),
        Count=("us_aqi", "count")
    )

    daily = daily[daily["Count"] == 24][["AQI"]]
    daily = daily.asfreq("D")

    if len(daily) < 8 or daily["AQI"].tail(8).isna().any():
        st.error("Insufficient complete daily data.")
        st.stop()

    latest_date = daily.index[-1]

    st.subheader("Historical Air Quality")

    st.caption(
        f"Daily mean of hourly US AQI estimates, "
        f"through {latest_date:%d %B %Y}"
    )

    st.line_chart(daily["AQI"].tail(14))

    features_df = daily.copy()
    features_df["Month"] = features_df.index.month
    features_df["Day"] = features_df.index.day
    features_df["DayOfWeek"] = features_df.index.dayofweek

    for lag in [1, 3, 7]:
        features_df[f"AQI_Lag{lag}"] = (
            features_df["AQI"].shift(lag)
        )

    features_df["AQI_Rolling3"] = (
        features_df["AQI"].shift(1).rolling(3).mean()
    )

    features_df["AQI_Rolling7"] = (
        features_df["AQI"].shift(1).rolling(7).mean()
    )

    latest = features_df.iloc[[-1]]
    features = saved["features"]

    if latest[features].isna().any().any():
        st.error("Missing features for forecasting.")
        st.stop()

    st.subheader("Machine Learning Forecasts")

    model_names = {
        1: "Linear Regression",
        3: "Linear Regression",
        7: "Gradient Boosting"
    }

    forecast_rows = []
    cols = st.columns(3)

    for i, h in enumerate([1, 3, 7]):
        model = saved["models"][h]
        prediction = float(
            model.predict(latest[features])[0]
        )
        prediction = max(0, prediction)

        forecast_date = latest_date + timedelta(days=h)

        cols[i].metric(
            f"{h}-Day Forecast",
            f"{prediction:.0f} AQI"
        )
        cols[i].caption(
            f"{forecast_date:%d %b %Y} | "
            f"{model_names[h]}"
        )
        cols[i].write(get_category(prediction))

        forecast_rows.append({
            "Date": forecast_date,
            "Predicted AQI": prediction,
            "Horizon": f"{h} Day",
            "Model": model_names[h]
        })

    forecast_df = pd.DataFrame(forecast_rows)

    st.subheader("Forecast Timeline")
    st.line_chart(
        forecast_df.set_index("Date")["Predicted AQI"]
    )

    st.dataframe(
        forecast_df,
        hide_index=True,
        use_container_width=True
    )

    st.info(
        "Experimental forecasts based on historical "
        "Open-Meteo US AQI estimates. These predictions "
        "are not official air-quality warnings. "
        "Longer-horizon models have limited validation performance."
    )

    st.caption(
        "Data source: Open-Meteo Air Quality API. "
        "The current value and historical daily averages "
        "are API estimates; future values are generated "
        "by separately trained ML models."
    )

except Exception as e:
    st.error(f"Dashboard error: {e}")
