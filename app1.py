from flask import Flask
from datetime import datetime, timedelta
import math
import requests
import threading

app = Flask(__name__)

# -----------------------------
# LOKALIZACJA: GDYNIA
# -----------------------------
LAT = 54.52
LON = 18.53

# Jeśli chcesz liczyć czas "lokalny" (CET/CEST), ustaw przesunięcie.
# Teraz (zima) CET = UTC+1. Gdy przyjdzie czas letni, zmień na 2.
TZ_OFFSET_HOURS = 1  # CET

# -----------------------------
# KONFIGURACJA DOBOWYCH ZUŻYĆ
# -----------------------------
# WODA
WATER_TOTAL_D = 12.0      # m3 / doba (cel dobowy)
WATER_BASE_D  = 2.0       # m3 / doba (baza 24/7)
WATER_ADD_D   = WATER_TOTAL_D - WATER_BASE_D  # m3 / doba, część "robocza" 6–22

# ENERGIA
ENERGY_TOTAL_D = 5085.0   # kWh / doba (cel dobowy)
ENERGY_BASE_D  = 2200.0   # kWh / doba (baza 24/7)
ENERGY_ADD_D   = ENERGY_TOTAL_D - ENERGY_BASE_D  # kWh / doba, część "robocza" 6–22

WORK_START = 6.0   # 6:00
WORK_END   = 22.0  # 22:00
WORK_SPAN  = WORK_END - WORK_START  # 16 h

# -----------------------------
# CACHE Open‑Meteo (60 s)
# -----------------------------
_cache = {"ts": None, "outdoor": None, "humidity": None}
_cache_lock = threading.Lock()
CACHE_TTL = timedelta(seconds=60)

def now_local():
    """Zwraca 'czas lokalny' (CET/CEST wg TZ_OFFSET_HOURS) jako datetime."""
    return datetime.utcnow() + timedelta(hours=TZ_OFFSET_HOURS)

def open_meteo_current():
    """
    Pobiera temp. zewnętrzną i wilgotność z Open‑Meteo (Gdynia).
    Zwraca (outdoor_temp, humidity). W razie problemu pamięta ostatnią, a jak brak – 0.
    """
    now = datetime.utcnow()
    with _cache_lock:
        if _cache["ts"] and now - _cache["ts"] < CACHE_TTL:
            return _cache["outdoor"], _cache["humidity"]

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,relative_humidity_2m"
    )
    try:
        data = requests.get(url, timeout=4).json()
        cur = data.get("current", {})
        outdoor = cur.get("temperature_2m")
        humidity = cur.get("relative_humidity_2m")

        with _cache_lock:
            _cache["ts"] = datetime.utcnow()
            _cache["outdoor"] = outdoor
            _cache["humidity"] = humidity

        return outdoor, humidity
    except Exception:
        with _cache_lock:
            return _cache["outdoor"] or 0, _cache["humidity"] or 0

# -----------------------------
# TEMPERATURA HALI – SYMULACJA
# -----------------------------
def simulate_indoor_temp():
    """
    20°C rano, szczyt ~22.8°C ok. 14:00, wieczorem >= 21.2°C.
    Weekend odrobinę chłodniejszy.
    """
    now = now_local()
    weekday = now.weekday()  # pon=0 ... niedz=6
    hour = now.hour + now.minute/60 + now.second/3600

    # Parametry
    night_temp = 20.0
    peak_temp = 22.8
    evening_floor = 21.2

    if weekday >= 5:  # sob/niedz
        night_temp = 19.8
        peak_temp = 21.7
        evening_floor = 21.0

    peak_hour = 14.0
    amplitude = max(0.1, peak_temp - night_temp)
    temp = night_temp + amplitude * math.sin((math.pi/12) * (hour - peak_hour) + math.pi/2)

    if hour >= 17.0:
        temp = max(temp, evening_floor)

    # Drobne "mikrodrgania" ±0.15°C
    micro = ((now.minute % 10) - 5) * 0.03
    temp += micro

    return round(temp, 1)

# -----------------------------
# FUNKCJE POMOCNICZE – KUMULACJA DZIENNA
# -----------------------------
def hours_since_midnight_local():
    """Godziny od północy (lokalnie), z ułamkiem."""
    now = now_local()
    return now.hour + now.minute/60 + now.second/3600

def cumulative_base_today(total_base_24h, h):
    """Baza rozłożona równomiernie na 24h."""
    rate = total_base_24h / 24.0
    return rate * max(0.0, min(24.0, h))

def cumulative_additional_today(total_additional_16h, h):
    """
    Część "robocza" 6–22: rozkład sinus od 0 (6:00) do 0 (22:00), szczyt w połowie.
    Cumulatywna frakcja od 6 do godziny h: (1 - cos(pi*x)) / 2, gdzie x=(h-6)/16.
    """
    if h <= WORK_START:
        return 0.0
    if h >= WORK_END:
        return total_additional_16h
    x = (h - WORK_START) / WORK_SPAN  # 0..1
    frac = (1.0 - math.cos(math.pi * x)) / 2.0  # 0..1
    return total_additional_16h * frac

def cumulative_today(total_base_24h, total_additional_16h):
    """Kumulacja (baza + robocza) od północy do 'teraz' (czas lokalny)."""
    h = hours_since_midnight_local()
    base = cumulative_base_today(total_base_24h, h)
    add  = cumulative_additional_today(total_additional_16h, h)
    return base + add

# -----------------------------
# ENDPOINTY – JSON {"value":"..."}
# -----------------------------
@app.route("/temp")
def temp():
    t = simulate_indoor_temp()
    return {"value": str(t)}

@app.route("/outdoor")
def outdoor():
    t, _ = open_meteo_current()
    return {"value": str(t)}

@app.route("/humidity")
def humidity():
    _, h = open_meteo_current()
    return {"value": str(h)}

@app.route("/water")
def water_cumulative():
    """
    Zwraca skumulowane dzisiejsze zużycie wody (m3) od północy, jako JSON {"value":"x.xx"}.
    Docelowo o 24:00 będzie to ~12.00 m3.
    """
    val = cumulative_today(WATER_BASE_D, WATER_ADD_D)
    return {"value": f"{val:.2f}"}

@app.route("/energy")
def energy_cumulative():
    """
    Zwraca skumulowane dzisiejsze zużycie energii (kWh) od północy, jako JSON {"value":"xxxx"}.
    Docelowo o 24:00 będzie to ~5085 kWh.
    """
    val = cumulative_today(ENERGY_BASE_D, ENERGY_ADD_D)
    # energia zwykle w pełnych kWh, ale możesz zmienić na 1 miejsce: f"{val:.1f}"
    return {"value": f"{val:.0f}"}

@app.route("/")
def root():
    return {
        "status": "OK",
        "timezone_offset_hours": TZ_OFFSET_HOURS,
        "endpoints": {
            "/temp":     "symulowana temperatura hali [°C]",
            "/outdoor":  "temperatura zewnętrzna (Open‑Meteo, Gdynia) [°C]",
            "/humidity": "wilgotność zewnętrzna (Open‑Meteo, Gdynia) [%]",
            "/water":    "dzienne zużycie wody od północy [m3]",
            "/energy":   "dzienne zużycie energii od północy [kWh]"
        },
        "format": "{\"value\":\"...\"}",
        "work_hours": "06:00–22:00",
        "daily_targets": {"water_m3": WATER_TOTAL_D, "energy_kWh": ENERGY_TOTAL_D},
        "base_load": {"water_m3_per_day": WATER_BASE_D, "energy_kWh_per_day": ENERGY_BASE_D}
    }

if __name__ == "__main__":
    # Lokalnie: python app.py
    app.run(host="0.0.0.0", port=5000)
