from flask import Flask, Response
from datetime import datetime, timedelta
import math
import requests
import threading

app = Flask(__name__)

LAT = 54.52
LON = 18.53

# -------------------------------------
# CACHE Open-Meteo (60 sek)
# -------------------------------------
_cache = {"ts": None, "outdoor": None, "humidity": None}
_cache_lock = threading.Lock()
CACHE_TTL = timedelta(seconds=60)

def fetch_open_meteo():
    now = datetime.utcnow()
    with _cache_lock:
        if _cache["ts"] and now - _cache["ts"] < CACHE_TTL:
            return _cache["outdoor"], _cache["humidity"]

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&current=temperature_2m,relative_humidity_2m"
        )
        data = requests.get(url, timeout=4).json()
        current = data.get("current", {})
        outdoor = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")

        with _cache_lock:
            _cache["ts"] = datetime.utcnow()
            _cache["outdoor"] = outdoor
            _cache["humidity"] = humidity

        return outdoor, humidity
    except:
        with _cache_lock:
            return _cache["outdoor"] or 0, _cache["humidity"] or 0

# -------------------------------------
# SYMULACJA TEMPERATURY HALI
# -------------------------------------
def simulate_indoor_temp():
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour + now.minute/60.0

    night_temp = 20.0
    peak_temp = 22.8
    evening_floor = 21.2

    if weekday >= 5:
        night_temp = 19.8
        peak_temp = 21.7
        evening_floor = 21.0

    peak_hour = 14
    amplitude = max(0.1, peak_temp - night_temp)
    temp = night_temp + amplitude * math.sin((math.pi/12)*(hour - peak_hour) + math.pi/2)

    if hour >= 17:
        temp = max(temp, evening_floor)

    micro = ((now.minute % 10) - 5) * 0.03
    temp += micro

    return round(temp, 1)

# -------------------------------------
# ENDPOINTY
# -------------------------------------
@app.route("/temp")
def temp():
    return Response(str(simulate_indoor_temp()), mimetype="text/plain")

@app.route("/outdoor")
def outdoor():
    o, _ = fetch_open_meteo()
    return Response(str(o or 0), mimetype="text/plain")

@app.route("/humidity")
def humidity():
    _, h = fetch_open_meteo()
    return Response(str(h or 0), mimetype="text/plain")

@app.route("/datetime")
def datetime_plain():
    return Response(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mimetype="text/plain")

@app.route("/")
def root():
    return Response("Endpointy: /temp /outdoor /humidity /datetime",
                    mimetype="text/plain")

# -------------------------------------
# URUCHOMIENIE
# -------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
