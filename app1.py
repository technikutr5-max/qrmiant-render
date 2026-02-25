from flask import Flask

app = Flask(__name__)

# -----------------------------
#  ZWYKŁE, STATYCZNE ENDPOINTY Z JSON
#  ZWRACAJĄ DOKŁADNIE {"value": "25"}
# -----------------------------

@app.route("/temp")
def temp():
    return {"value": "25"}

@app.route("/humidity")
def humidity():
    return {"value": "25"}

@app.route("/outdoor")
def outdoor():
    return {"value": "25"}

@app.route("/datetime")
def datetime_value():
    return {"value": "25"}

# -----------------------------
# ROOT - STRONA GŁÓWNA
# -----------------------------
@app.route("/")
def root():
    return {
        "available_endpoints": [
            "/temp",
            "/humidity",
            "/outdoor",
            "/datetime"
        ],
        "format": "Each endpoint returns JSON: {\"value\": \"25\"}"
    }

# -----------------------------
# URUCHOMIENIE (Render używa gunicorn)
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
