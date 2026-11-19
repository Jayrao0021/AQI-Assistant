import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Wind, House, ChartNoAxesCombined, MapPin, Bell, Settings, PanelLeftClose, PanelLeftOpen, Search, LocateFixed, Activity, Droplets, CalendarDays, Clock3, CheckCircle2, X, UserRound, ArrowUpRight, ShieldAlert, Lightbulb, BrainCircuit, TrendingDown, Info, HeartPulse } from 'lucide-react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import './App.css'

// Guidance for the modeled Indian AQI series.
const advice = {
  Good: 'Air quality is good. Normal outdoor activities are generally suitable.',
  Satisfactory: 'Air quality is satisfactory. Sensitive people may experience minor breathing discomfort.',
  Moderate: 'People with asthma or heart or lung conditions, children, and older adults may experience breathing discomfort during prolonged outdoor activity.',
  Poor: 'Breathing discomfort may occur with prolonged exposure. Consider reducing strenuous outdoor activity.',
  'Very Poor': 'Respiratory illness may occur with prolonged exposure. Limit outdoor exertion and follow local health guidance.',
  Severe: 'Air quality can affect even healthy people and seriously impact those with existing conditions. Avoid outdoor exertion and follow official advisories.'
}
const insights = [
  { icon: ShieldAlert, title: 'Health advisory', description: advice.Moderate, foot: 'General guidance for sample Indian AQI · CPCB category' },
  { icon: TrendingDown, title: 'What the trend shows', description: 'The illustrative AQI fell from 225 to 168 over the seven displayed days, with fluctuations along the way.', foot: 'Illustrative Indian AQI history · not live measurements' },
  { icon: BrainCircuit, title: 'Understanding the forecast', description: 'Experimental 1/3/7-day predictions use models trained on 2024–2026 Open-Meteo estimates for five cities, not station measurements.', foot: 'Modeled Indian AQI · experimental ML predictions' },
  { icon: Lightbulb, title: 'Practical recommendations', description: 'If you are sensitive to air pollution, consider shorter outdoor workouts, check local air-quality advisories, and reduce exposure during pollution peaks.', foot: 'General information · not personalized medical advice' },
]
const pages = [
  { label: 'Dashboard', icon: House }, { label: 'Forecast', icon: ChartNoAxesCombined },
  { label: 'Map & Route', icon: MapPin }, { label: 'Alerts', icon: Bell },
]
function category(aqi) {
  if (aqi <= 50) return 'Good'
  if (aqi <= 100) return 'Satisfactory'
  if (aqi <= 200) return 'Moderate'
  if (aqi <= 300) return 'Poor'
  if (aqi <= 400) return 'Very Poor'
  return 'Severe'
}
function Glass({ children, className = '', delay = 0 }) {
  const ref = useRef(null)
  const onMove = (e) => {
    if (!ref.current) return
    const r = ref.current.getBoundingClientRect()
    ref.current.style.setProperty('--light-x', `${e.clientX - r.left}px`)
    ref.current.style.setProperty('--light-y', `${e.clientY - r.top}px`)
  }
  return <motion.div ref={ref} onMouseMove={onMove} className={`glass-card interactive-glass ${className}`}
    initial={{ opacity: 0, y: 25, scale: .97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
    transition={{ type: 'spring', stiffness: 180, damping: 21, delay }}
    whileHover={{ y: -5, transition: { duration: .2 } }}>{children}</motion.div>
}
// Original vector illustration, drawn in JSX. No image download or API required.
function IndiaGate() {
  return <svg className="landmark-svg" viewBox="0 0 470 250" role="img" aria-label="Stylized illustration of India Gate in Delhi">
    <defs>
      <linearGradient id="gateStone" x1="0" x2="1" y1="0" y2="1"><stop stopColor="#ffd5dc"/><stop offset="1" stopColor="#e884a4"/></linearGradient>
      <linearGradient id="cityFade" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#f9a5c1"/><stop offset="1" stopColor="#d34e87"/></linearGradient>
    </defs>
    <g fill="url(#cityFade)" opacity=".52">
      <path d="M0 217v-30h13v-16h12v22h10v-39h15v13h13v32h14v-27h11v-20h14v43h18v-14h12v36z"/>
      <path d="M340 216v-28h15v-18h12v20h13v-40h12v14h16v37h11v-30h12v-13h15v42h24v16z"/>
      <path d="M22 219v-13h426v13z"/>
    </g>
    <g fill="url(#gateStone)" stroke="#fbd2df" strokeWidth="2">
      <path d="M168 219V96h17V75h15V61h70v14h15v21h17v123h-42v-73a25 25 0 0 0-50 0v73z" fillRule="evenodd"/>
      <path d="M181 93h108v10H181zM194 75h82v9h-82zM207 61h56v8h-56z"/>
      <path d="M185 108h15v111h-15zM270 108h15v111h-15z" opacity=".55"/>
      <path d="M157 219h156v10H157z"/>
    </g>
    <path d="M205 219v-72a30 30 0 0 1 60 0v72z" fill="#e76398" opacity=".55"/>
    <path d="M0 230h470v20H0z" fill="#d64b85" opacity=".3"/>
    <path d="M235 230l-22 20h44z" fill="#ffccda" opacity=".45"/>
  </svg>
}
export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [page, setPage] = useState('Dashboard')
  const [search, setSearch] = useState('')
  const [period, setPeriod] = useState('7D')
  const [forecastData, setForecastData] = useState([])
  const [forecastLoading, setForecastLoading] = useState(false)
  const [forecastError, setForecastError] = useState('')
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const [popup, setPopup] = useState('')
  const [selectedLocation, setSelectedLocation] = useState({name: 'Delhi', country: 'India', latitude: 28.6139, longitude: 77.2090})
  const [airData, setAirData] = useState(null)
  const [stationData, setStationData] = useState(null)
  const [stationLoading, setStationLoading] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searching, setSearching] = useState(false)
  const [locating, setLocating] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const hasStation = stationData?.status === 'available' && typeof stationData.us_aqi === 'number'
  const aqi = hasStation ? stationData.us_aqi : (typeof airData?.indian_aqi === 'number' ? airData.indian_aqi : null)
  const currentCategory = aqi === null ? 'Unavailable' : (hasStation ? stationData.us_aqi_category : (airData?.indian_aqi_category || category(aqi)))
  const aqiStandard = hasStation ? 'US AQI · nearby station' : 'Indian AQI · modeled estimate'
  const stationPm25 = stationData?.pollutant_averages?.pm25?.average_24h
  const stationPm10 = stationData?.pollutant_averages?.pm10?.average_24h
  const usAdvice = { Good: 'Air quality is good.', Moderate: 'Unusually sensitive people should consider limiting prolonged outdoor exertion.', 'Unhealthy for Sensitive Groups': 'Sensitive groups should reduce prolonged or heavy outdoor exertion.', Unhealthy: 'Everyone should consider reducing prolonged outdoor exertion, especially sensitive groups.', 'Very Unhealthy': 'Avoid prolonged outdoor exertion and follow local air-quality advisories.', Hazardous: 'Avoid outdoor physical activity and follow local emergency advisories.' }
  const fmt = (value) => typeof value === 'number' ? value.toFixed(1) : '—'
  const loadAir = useCallback(async (location, signal) => {
    setLoading(true)
    setError('')
    setAirData(null)
    try {
      const params = new URLSearchParams({latitude: String(location.latitude), longitude: String(location.longitude)})
      const response = await fetch(`http://127.0.0.1:8000/api/air-quality?${params}`, {signal})
      if (!response.ok) throw new Error(`Air-quality API returned ${response.status}`)
      const data = await response.json()
      setAirData(data)
      if (data.indian_aqi == null) setError(data.indian_aqi_status || 'Indian AQI is unavailable for this location.')
    } catch (err) {
      if (err.name !== 'AbortError') setError('Could not load air quality. Check that the FastAPI backend is running on port 8000.')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    loadAir(selectedLocation, controller.signal)
    return () => controller.abort()
  }, [selectedLocation, loadAir])
  useEffect(() => {
    const controller = new AbortController()
    setStationData(null)
    setStationLoading(true)
    const params = new URLSearchParams({latitude: String(selectedLocation.latitude), longitude: String(selectedLocation.longitude)})
    fetch(`http://127.0.0.1:8000/api/station-air-quality?${params}`, {signal: controller.signal})
      .then(response => { if (!response.ok) throw new Error('Station endpoint unavailable'); return response.json() })
      .then(data => { if (!controller.signal.aborted) setStationData(data) })
      .catch(() => { if (!controller.signal.aborted) setStationData({status: 'provider_unavailable'}) })
      .finally(() => { if (!controller.signal.aborted) setStationLoading(false) })
    return () => controller.abort()
  }, [selectedLocation])
  useEffect(() => {
    const controller = new AbortController()
    const fetchHistory = async () => {
      setHistoryLoading(true)
      setHistoryError('')
      setHistory([])
      try {
        const params = new URLSearchParams({
          latitude: String(selectedLocation.latitude),
          longitude: String(selectedLocation.longitude),
          days: period.replace('D', ''),
        })
        const response = await fetch(`http://127.0.0.1:8000/api/history?${params}`, {signal: controller.signal})
        if (!response.ok) throw new Error(`History API returned ${response.status}`)
        const data = await response.json()
        if (!controller.signal.aborted) setHistory((data.history || []).map(item => ({
          ...item,
          day: new Date(`${item.date}T12:00:00`).toLocaleDateString('en-IN', {day: 'numeric', month: 'short'}),
        })))
      } catch (err) {
        if (err.name !== 'AbortError') setHistoryError('Historical data is temporarily unavailable.')
      } finally {
        if (!controller.signal.aborted) setHistoryLoading(false)
      }
    }
    fetchHistory()
    return () => controller.abort()
  }, [selectedLocation, period])
  useEffect(() => {
    const controller = new AbortController()
    const loadForecast = async () => {
      setForecastData([])
      setForecastError('')
      setForecastLoading(true)
      try {
        const params = new URLSearchParams({latitude: String(selectedLocation.latitude), longitude: String(selectedLocation.longitude)})
        const response = await fetch(`http://127.0.0.1:8000/api/forecast?${params}`, {signal: controller.signal})
        const result = await response.json()
        if (!response.ok) throw new Error(result.detail || `Forecast API returned ${response.status}`)
        if (!controller.signal.aborted) setForecastData(result.predictions || [])
      } catch (err) {
        if (err.name !== 'AbortError' && !controller.signal.aborted) setForecastError(err.message || 'Forecast service unavailable.')
      } finally {
        if (!controller.signal.aborted) setForecastLoading(false)
      }
    }
    loadForecast()
    return () => controller.abort()
  }, [selectedLocation])
  const validHistory = history.filter(item => typeof item.aqi === 'number')
  const trendDescription = historyLoading ? 'Loading historical estimates…' : historyError ? historyError : validHistory.length >= 2
    ? `Estimated Indian AQI ${validHistory.at(-1).aqi >= validHistory[0].aqi ? 'rose' : 'fell'} from ${validHistory[0].aqi} to ${validHistory.at(-1).aqi} across the selected period. These are modeled daily estimates, not official station measurements.`
    : 'Not enough historical observations to describe the trend.'
  const chooseLocation = (location) => {
    setSelectedLocation(location)
    setSearch('')
    setSuggestions([])
    setShowSuggestions(false)
  }
  const findCities = async () => {
    if (search.trim().length < 2) { setPopup('Enter at least two characters to search for a city.'); return }
    setSearching(true)
    setShowSuggestions(true)
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/locations?query=${encodeURIComponent(search.trim())}`)
      if (!response.ok) throw new Error('Search failed')
      const cities = await response.json()
      setSuggestions(cities)
      if (!cities.length) setPopup('No matching cities found. Try another spelling.')
    } catch { setPopup('City search failed. Make sure the backend is running.') }
    finally { setSearching(false) }
  }
  const useMyLocation = () => {
    if (!navigator.geolocation) { setPopup('Your browser does not support geolocation.'); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      ({coords}) => { chooseLocation({name: 'My Location', country: '', latitude: coords.latitude, longitude: coords.longitude}); setLocating(false) },
      (err) => { setLocating(false); setPopup(err.code === 1 ? 'Location permission was denied.' : 'Could not determine your location. Try searching for a city.') },
      {enableHighAccuracy: false, timeout: 12000, maximumAge: 300000}
    )
  }
  const openPreview = (name) => setPopup(`${name} is not implemented yet.`)
  return <div className="app-shell landmark-layout">
    <div className="background-orb orb-one"/><div className="background-orb orb-two"/><div className="background-orb orb-three"/>
    <div className="ambient-wave wave-one"/><div className="ambient-wave wave-two"/>
    <motion.aside className="sidebar" animate={{ width: collapsed ? 85 : 226 }} transition={{ type: 'spring', stiffness: 270, damping: 25 }}>
      <div className="sidebar-top"><div className="brand-symbol"><Wind size={34}/></div>{!collapsed && <div className="brand-text"><strong>AQI Assistant</strong><span>Air quality intelligence</span></div>}</div>
      <button className="collapse-button press-spring" aria-label="Toggle sidebar" onClick={() => setCollapsed(!collapsed)}>{collapsed ? <PanelLeftOpen size={20}/> : <PanelLeftClose size={20}/>}</button>
      <nav className="sidebar-nav">{pages.map(({label,icon:Icon}) => <motion.button key={label} className={`nav-item ${page === label ? 'active' : ''}`} onClick={() => {setPage(label); if(label !== 'Dashboard') openPreview(label)}} whileHover={{x:4}} whileTap={{scale:.94}} title={label}><Icon size={21}/>{!collapsed && <span>{label}</span>}</motion.button>)}</nav>
      <div className="sidebar-bottom"><button className="nav-item" onClick={() => {setPage('Settings');openPreview('Settings')}}><Settings size={22}/>{!collapsed && <span>Settings</span>}</button></div>
    </motion.aside>
    <main className="main-content">
      <header className="top-header"><div><h1>Air Quality Intelligence</h1><p>Your air, your awareness. <span className="subtitle-swoosh"/></p></div><div className="header-actions"><button className="icon-button" onClick={() => openPreview('Notifications')} aria-label="Notifications"><Bell size={24}/><span className="notification-dot"/></button><button className="avatar" onClick={() => openPreview('Profile')} aria-label="Profile"><UserRound size={24}/></button></div></header>
      <div className="search-row"><div className="search-box glass-surface animated-search" style={{position:'relative'}}><button onClick={findCities} aria-label="Search cities" style={{background:'none',border:0,cursor:'pointer',color:'inherit',display:'flex',alignItems:'center'}}><Search size={25}/></button><input aria-label="Search city" value={search} onChange={e=>{setSearch(e.target.value);setShowSuggestions(false)}} onKeyDown={e=>{if(e.key==='Enter')findCities()}} placeholder="Search for a city or location..."/>{search && <button onClick={()=>{setSearch('');setSuggestions([]);setShowSuggestions(false)}} aria-label="Clear search"><X size={17}/></button>}{searching && <span style={{fontSize:12}}>Searching…</span>}{showSuggestions && suggestions.length > 0 && <div role="listbox" aria-label="City results" style={{position:'absolute',top:'calc(100% + 8px)',left:0,right:0,zIndex:60,background:'rgba(255,255,255,.94)',backdropFilter:'blur(18px)',border:'1px solid #dfcafa',borderRadius:14,boxShadow:'0 12px 30px #4d25802b',maxHeight:220,overflowY:'auto',padding:6}}>{suggestions.map((city,i)=><button key={`${city.latitude}-${city.longitude}-${i}`} role="option" aria-selected={false} onClick={()=>chooseLocation(city)} style={{display:'block',width:'100%',textAlign:'left',padding:'10px 12px',border:0,borderRadius:10,background:'transparent',color:'#3d2365',cursor:'pointer'}}>{city.name}{city.admin1 ? `, ${city.admin1}` : ''}, {city.country}</button>)}</div>}</div><button className="location-button glass-surface press-spring" onClick={useMyLocation} disabled={locating}><LocateFixed size={22}/>{locating ? 'Locating…' : 'Use My Location'}</button></div>
      {error && !hasStation && <div role="alert" style={{margin:'10px 0',padding:'12px 16px',borderRadius:14,background:'rgba(255,255,255,.75)',color:'#8a2452'}}>{error} <button onClick={()=>loadAir(selectedLocation)} style={{marginLeft:12,cursor:'pointer'}}>Retry</button></div>}
       <div className="hero-grid">
        <Glass className="location-panel" delay={.06}><div className="location-title"><MapPin size={28}/><div><h2>{selectedLocation.name}{selectedLocation.country ? `, ${selectedLocation.country}` : ''}</h2><p>{loading ? 'Loading modeled air-quality estimates…' : hasStation ? `Station: ${stationData.station || 'Unnamed'} · ${stationData.provider || 'OpenAQ'} · ${stationData.official_cpcb_station ? 'CPCB' : 'non-CPCB / unverified'}` : stationLoading ? 'Checking nearby monitoring stations…' : 'Modeled Indian AQI · no qualified recent station available'}</p></div></div><div className="location-body"><div className="aqi-card"><span>{aqiStandard}</span><motion.div className="aqi-number" initial={{scale:.8,opacity:0}} animate={{scale:1,opacity:1}} transition={{type:'spring',delay:.25}}>{loading && !hasStation ? "…" : (aqi ?? "—")}</motion.div><span className="aqi-category">{loading && !hasStation ? "Loading" : currentCategory}</span>{selectedLocation.name.toLowerCase() === "delhi" ? <IndiaGate/> : <div style={{minHeight:90,display:"flex",alignItems:"end",justifyContent:"center",fontSize:12,opacity:.7}}>Location-specific landmark coming soon</div>}</div><div className="pollutant-stack"><div className="pollutant"><Droplets size={26}/><div><strong>PM2.5</strong><b>{loading ? "…" : fmt(hasStation ? stationPm25 : airData?.pollutants?.pm2_5)} <small>µg/m³</small></b></div></div><div className="pollutant"><Wind size={26}/><div><strong>PM10</strong><b>{loading ? "…" : fmt(hasStation ? stationPm10 : airData?.pollutants?.pm10)} <small>µg/m³</small></b></div></div></div></div></Glass>
        <Glass className="chart-card" delay={.14}><div className="section-header"><h2><ChartNoAxesCombined size={25}/>Air Quality Trend</h2><div className="period-switch">{['7D','14D','30D'].map(item=><button key={item} className={period===item?'selected':''} aria-label={`${item} history`} onClick={()=>setPeriod(item)}>{item}</button>)}</div></div><p style={{fontSize:12,opacity:.75,margin:'4px 0'}}>{historyLoading ? 'Loading historical estimates…' : historyError || 'Historical Indian AQI estimates · Open-Meteo modeled data · not official CPCB'}</p><div className="chart-area"><ResponsiveContainer width="100%" height="100%"><AreaChart data={history} margin={{top:12,right:12,bottom:0,left:-20}}><defs><linearGradient id="aqiFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8e3fe8" stopOpacity={.35}/><stop offset="100%" stopColor="#8e3fe8" stopOpacity={.02}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#d8c7f4" strokeDasharray="4 4"/><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{fill:'#4f328c',fontSize:11}}/><YAxis domain={[0,500]} tickLine={false} axisLine={false} tick={{fill:'#4f328c',fontSize:11}}/><Tooltip contentStyle={{borderRadius:16,background:'rgba(255,255,255,.92)',border:'1px solid #e4d2fc'}}/><Area type="monotone" connectNulls={false} dataKey="aqi" stroke="#8433e5" strokeWidth={3.5} fill="url(#aqiFill)" dot={{r:4,fill:'#8433e5',stroke:'#fff',strokeWidth:2}} activeDot={{r:7}} animationDuration={1000}/></AreaChart></ResponsiveContainer></div></Glass>
      </div>
      <section className="forecast-section"><div className="section-header forecast-heading"><h2><CalendarDays size={27}/> AQI Forecast</h2><span>Experimental 5-city ML · Indian AQI · 2024–2026 modeled training data</span></div><div className="forecast-grid">{[1,3,7].map((days,i) => { const item = forecastData.find(p => p.horizon_days === days); return <Glass className="forecast-card" key={days} delay={.24+i*.07}><div className="forecast-title"><CalendarDays size={22}/>{days}-Day Forecast</div><div className="forecast-number">{forecastLoading ? '…' : item ? item.aqi : '—'} {item && <small>AQI</small>}</div><div className="forecast-date">{item ? new Date(`${item.date}T12:00:00`).toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}) : (forecastError || 'Awaiting experimental prediction')}</div><div className="forecast-status">{item ? `${item.category} · Experimental` : 'Unavailable'}</div></Glass>})}</div><p style={{fontSize:12,opacity:.8,marginTop:10}}>Research-only Indian AQI forecasts trained on modeled Open-Meteo data (2024–2026). These do not predict station-based US AQI. Do not rely on them for health decisions.</p></section>
      <section className="insights-section" aria-label="Air quality explanations">
        <div className="insights-heading">
          <div><h2><HeartPulse size={20}/> Your air, explained</h2><p>Helpful context beyond the numbers</p></div>
          <span className="insights-sample"><Info size={14}/> Station-based US AQI when available · modeled Indian AQI history and forecasts</span>
        </div>
        <div className="insights-grid">
          {insights.map(({icon: Icon, title, description, foot}, index) => (
            <Glass key={title} className="insight-card" delay={.36 + index * .055}>
              <div className="insight-top"><span className="insight-icon"><Icon size={19}/></span><h3>{title}</h3></div>
              <p>{title === 'What the trend shows' ? trendDescription : title === 'Health advisory' && aqi !== null ? (hasStation ? (usAdvice[currentCategory] || 'Follow local air-quality advisories.') : advice[currentCategory]) : description}</p>
              <span className="insight-foot">{title === 'What the trend shows' ? 'Historical modeled Indian AQI · not official CPCB readings' : title === 'Health advisory' && aqi !== null ? (hasStation ? 'Provisional station-based US AQI · general guidance' : 'Modeled Indian AQI · general guidance') : foot}</span>
            </Glass>
          ))}
        </div>
      </section>
      <footer className="app-footer"><span>{hasStation ? `US AQI · provisional 24h PM estimate · ${stationData.station || 'nearby station'} · ${stationData.provider || 'OpenAQ'}` : 'Indian AQI · Open-Meteo modeled estimate (station unavailable)'}</span><span>{hasStation ? `Station observed: ${stationData.observed_at || 'unknown'} · not official citywide AQI` : (airData?.observed_at ? `Modeled data time: ${airData.observed_at} (${airData.timezone || 'local'})` : 'Awaiting air-quality data')} · Forecasts and history use modeled Indian AQI</span></footer>
    </main>
    <AnimatePresence>{popup && <motion.div role="status" className="preview-toast glass-surface" initial={{opacity:0,x:45,scale:.95}} animate={{opacity:1,x:0,scale:1}} exit={{opacity:0,x:45}}><CheckCircle2 size={23}/><div><strong>Design preview</strong><p>{popup}</p></div><button onClick={()=>setPopup('')} aria-label="Dismiss"><X size={20}/></button></motion.div>}</AnimatePresence>
  </div>
}
