
import streamlit as st
import pandas as pd
import requests
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="AQI Assistant",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], [data-testid="stApp"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
        radial-gradient(ellipse at 90% 5%, rgba(157,104,247,.28), transparent 36%),
        radial-gradient(ellipse at 90% 95%, rgba(255,90,139,.25), transparent 34%),
        radial-gradient(ellipse at 5% 85%, rgba(135,83,235,.24), transparent 38%),
        linear-gradient(135deg, #faf7ff 0%, #fffaff 55%, #f8efff 100%);
    color: #25104c;
}

.block-container {
    max-width: 1450px;
    padding-top: 1.7rem;
    padding-bottom: 3rem;
}

h1, h2, h3, p, label {
    color: #281451;
}

h1 {
    font-weight: 800;
    letter-spacing: -1.5px;
}

[data-testid="stSidebar"] {
    background: linear-gradient(
        160deg,
        rgba(130,64,215,.93),
        rgba(108,67,195,.82),
        rgba(174,112,230,.75)
    );
    border-right: 1px solid rgba(255,255,255,.55);
}

[data-testid="stSidebar"] * {
    color: white;
}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
    padding-top: 1rem;
}

[data-testid="stSidebar"] .stButton button {
    color: white;
    background: rgba(255,255,255,.15);
    border: 1px solid rgba(255,255,255,.35);
}

[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(255,255,255,.28);
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 27px !important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
    background: rgba(255,255,255,.44);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,.83);
    box-shadow: 0 9px 30px rgba(111,63,177,.10);
    transition: transform .25s ease, box-shadow .25s ease;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]):hover {
    box-shadow: 0 13px 35px rgba(111,63,177,.17);
}

[data-testid="stMetric"] {
    background: rgba(255,255,255,.35);
    border-radius: 22px;
    padding: 17px;
    border: 1px solid rgba(255,255,255,.65);
    transition: transform .22s ease, box-shadow .22s ease;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 25px rgba(110,65,190,.14);
}

[data-testid="stMetricValue"] {
    color: #351469;
    font-weight: 800;
}

.stButton button {
    border-radius: 18px;
    background: rgba(255,255,255,.55);
    border: 1px solid rgba(152,98,229,.35);
    color: #6931c4;
    font-weight: 600;
    transition: transform .18s ease, background .18s ease;
}

.stButton button:hover {
    background: rgba(220,198,255,.55);
    transform: translateY(-2px);
    color: #5723aa;
}

.stButton button:active {
    transform: scale(.97);
}

.stTextInput input {
    border-radius: 22px;
    background: rgba(255,255,255,.58);
    border: 1px solid rgba(150,95,225,.30);
    color: #29124f;
    padding: 12px 17px;
}

.stTextInput input:focus {
    border-color: #9557e8;
    box-shadow: 0 0 0 3px rgba(149,87,232,.12);
}

.hero {
    padding: 23px 28px;
    border-radius: 27px;
    color: white;
    background: linear-gradient(115deg, #ef4966, #f36b92 65%, #bd78db);
    box-shadow: 0 13px 30px rgba(231,71,117,.20);
}

.hero-label {
    font-size: 15px;
    font-weight: 600;
    opacity: .95;
}

.hero-number {
    font-size: clamp(55px, 6vw, 88px);
    line-height: 1.15;
    font-weight: 800;
    letter-spacing: -3px;
}

.hero-category {
    display: inline-block;
    padding: 7px 17px;
    border-radius: 30px;
    background: rgba(255,255,255,.88);
    color: #c52348;
    font-weight: 700;
}

.forecast-value {
    font-size: 35px;
    font-weight: 800;
    color: #351469;
}

.forecast-date {
    color: #705a94;
    font-size: 13px;
}

.pill {
    display: inline-block;
    padding: 5px 13px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
}

.subtitle {
    color: #7e6a9b;
    margin-top: -10px;
    margin-bottom: 20px;
}

footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


MODEL_PATH = Path(__file__).parent / "Live_AQI_Models.pkl"
DELHI_LAT = 28.6139
DELHI_LON = 77.2090


def category(aqi):
    if aqi <= 50:
        return "Good", "#159e66"
    if aqi <= 100:
        return "Moderate", "#e7a900"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups", "#ee8422"
    if aqi <= 200:
        return "Unhealthy", "#df3650"
    if aqi <= 300:
        return "Very Unhealthy", "#843ac4"
    return "Hazardous", "#871137"


@st.cache_resource
def load_models():
    return joblib.load(MODEL_PATH)


@st.cache_data(ttl=3600)
def search_city(query):
    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": query, "count": 8, "language": "en"},
        timeout=20
    )
    response.raise_for_status()
    return response.json().get("results", [])


@st.cache_data(ttl=1800)
def fetch_air_quality(lat, lon):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    yesterday = today - timedelta(days=1)

    response = requests.get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": (yesterday - timedelta(days=35)).isoformat(),
            "end_date": yesterday.isoformat(),
            "hourly": "us_aqi",
            "current": "us_aqi,pm2_5,pm10",
            "timezone": "Asia/Kolkata"
        },
        timeout=45
    )
    response.raise_for_status()
    return response.json()


def get_forecasts(daily):
    saved = load_models()

    features_df = daily.copy()
    features_df["Month"] = features_df.index.month
    features_df["Day"] = features_df.index.day
    features_df["DayOfWeek"] = features_df.index.dayofweek

    for lag in [1, 3, 7]:
        features_df[f"AQI_Lag{lag}"] = features_df["AQI"].shift(lag)

    features_df["AQI_Rolling3"] = (
        features_df["AQI"].shift(1).rolling(3).mean()
    )
    features_df["AQI_Rolling7"] = (
        features_df["AQI"].shift(1).rolling(7).mean()
    )

    latest = features_df.iloc[[-1]]
    features = saved["features"]

    if latest[features].isna().any().any():
        raise ValueError("Insufficient complete AQI history for forecasting.")

    forecasts = []

    for horizon in [1, 3, 7]:
        prediction = max(
            0,
            float(saved["models"][horizon].predict(latest[features])[0])
        )

        forecasts.append({
            "horizon": horizon,
            "aqi": round(prediction),
            "date": daily.index[-1] + timedelta(days=horizon)
        })

    return forecasts


if "location" not in st.session_state:
    st.session_state.location = {
        "name": "Delhi",
        "country": "India",
        "latitude": DELHI_LAT,
        "longitude": DELHI_LON
    }

if "page" not in st.session_state:
    st.session_state.page = "Dashboard"


with st.sidebar:
    st.markdown("## 🌬️ AQI Assistant")
    st.write("Your air, your awareness.")
    st.divider()

    for page, symbol in [
        ("Dashboard", "🏠"),
        ("Forecast", "📈"),
        ("Map & Route", "📍"),
        ("Alerts", "🔔")
    ]:
        if st.button(
            f"{symbol}  {page}",
            use_container_width=True,
            key=f"nav_{page}"
        ):
            st.session_state.page = page
            st.rerun()

    st.divider()
    st.caption("Experimental air quality intelligence")


st.title("Air Quality Intelligence")
st.markdown(
    '<div class="subtitle">Your air, your awareness. '
    '✦ Live US AQI estimates and experimental forecasts</div>',
    unsafe_allow_html=True
)

search_col, refresh_col = st.columns([5, 1])

with search_col:
    search = st.text_input(
        "Search location",
        placeholder="🔎 Search for a city or location...",
        label_visibility="collapsed"
    )

with refresh_col:
    if st.button("↻ Refresh", use_container_width=True):
        fetch_air_quality.clear()
        st.rerun()


if search and len(search.strip()) >= 2:
    try:
        results = search_city(search.strip())

        if results:
            options = {
                f"{item['name']}, {item.get('admin1', '')}, "
                f"{item.get('country', '')}": item
                for item in results
            }

            selected = st.selectbox(
                "Select a location",
                ["Choose a location"] + list(options.keys())
            )

            if selected != "Choose a location":
                if st.button("View this location", type="primary"):
                    item = options[selected]
                    st.session_state.location = {
                        "name": item["name"],
                        "country": item.get("country", ""),
                        "latitude": item["latitude"],
                        "longitude": item["longitude"]
                    }
                    st.rerun()
        else:
            st.warning("No matching locations found.")

    except requests.RequestException:
        st.warning("Location search is temporarily unavailable.")


loc = st.session_state.location

st.markdown(
    f"### 📍 {loc['name']}, {loc['country']}"
)

page = st.session_state.page

if page in ["Map & Route", "Alerts"]:
    st.info(
        f"{page} is planned for a later implementation phase. "
        "The live AQI dashboard and city search are available now."
    )

else:
    try:
        api = fetch_air_quality(
            loc["latitude"],
            loc["longitude"]
        )

        current = api["current"]
        current_aqi = current.get("us_aqi")
        pm25 = current.get("pm2_5")
        pm10 = current.get("pm10")

        if current_aqi is None:
            st.error("Current AQI data is unavailable for this location.")
            st.stop()

        label, color = category(current_aqi)

        left, right = st.columns([1.4, 1])

        with left:
            st.markdown(
                f"""
                <div class="hero">
                    <div class="hero-label">CURRENT US AQI</div>
                    <div class="hero-number">{current_aqi:.0f}</div>
                    <span class="hero-category">{label}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

        with right:
            with st.container(border=True):
                st.metric(
                    "PM2.5",
                    f"{pm25:.1f} µg/m³" if pm25 is not None else "N/A"
                )
                st.metric(
                    "PM10",
                    f"{pm10:.1f} µg/m³" if pm10 is not None else "N/A"
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

        st.write("")
        st.subheader("📈 Air Quality Trend")

        with st.container(border=True):
            period = st.segmented_control(
                "Time period",
                options=[7, 14, 30],
                default=7,
                format_func=lambda n: f"{n} Days"
            )

            if period is None:
                period = 7

            st.line_chart(
                daily["AQI"].tail(period),
                color="#8239db",
                height=250
            )

        is_delhi = (
            abs(loc["latitude"] - DELHI_LAT) < 0.01
            and abs(loc["longitude"] - DELHI_LON) < 0.01
        )

        st.write("")
        st.subheader("🗓️ AQI Forecast")

        if is_delhi:
            forecasts = get_forecasts(daily)
            cols = st.columns(3)

            for col, forecast in zip(cols, forecasts):
                forecast_label, forecast_color = category(
                    forecast["aqi"]
                )

                with col:
                    with st.container(border=True):
                        st.markdown(
                            f"**{forecast['horizon']}-Day Forecast**"
                        )
                        st.markdown(
                            f'<div class="forecast-value">'
                            f'{forecast["aqi"]} AQI</div>',
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f'<div class="forecast-date">'
                            f'{forecast["date"]:%d %b %Y}</div>',
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f'<span class="pill" style="'
                            f'background:{forecast_color}22;'
                            f'color:{forecast_color}">'
                            f'{forecast_label}</span>',
                            unsafe_allow_html=True
                        )
        else:
            st.info(
                "Live air-quality data is available for this location. "
                "Our current ML forecasting models are trained for Delhi only."
            )

        st.caption(
            f"Last API estimate: {current.get('time')} "
            "(Asia/Kolkata). Data: Open-Meteo Air Quality API."
        )

        st.caption(
            "US AQI values are API estimates. Delhi ML forecasts "
            "are experimental and should not be used as official warnings."
        )

    except FileNotFoundError:
        st.error("Live_AQI_Models.pkl was not found in the project folder.")
    except Exception as e:
        st.error(f"Unable to load dashboard: {e}")
