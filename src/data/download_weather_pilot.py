
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import json

import pandas as pd


# 1. Definir las rutas del proyecto.
ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = ROOT / "data" / "raw" / "weather"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# 2. Configurar la consulta piloto.
API_URL = "https://archive-api.open-meteo.com/v1/archive"

params = {
    "latitude": -29.4131,
    "longitude": -66.8560,
    "start_date": "2022-06-30",
    "end_date": "2023-01-31",
    "hourly": ",".join([
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "precipitation"
    ]),
    "models": "era5",
    "timezone": "America/Argentina/La_Rioja",
    "temperature_unit": "celsius",
    "wind_speed_unit": "kmh",
    "precipitation_unit": "mm"
}


# 3. Construir y ejecutar la solicitud HTTP.
url = API_URL + "?" + urlencode(params)

print("Consultando Open-Meteo...")

with urlopen(url, timeout=60) as response:
    data = json.load(response)

if data.get("error"):
    raise RuntimeError(data.get("reason"))


# 4. Conservar la respuesta original.
raw_path = OUTPUT_DIR / "openmeteo_era5_spinup_pilot.json"

with open(raw_path, "w", encoding="utf-8") as file:
    json.dump(data, file, ensure_ascii=False, indent=2)


# 5. Transformar la respuesta en una tabla.
weather = pd.DataFrame(data["hourly"])

weather["time"] = pd.to_datetime(weather["time"])

csv_path = OUTPUT_DIR / "openmeteo_era5_spinup_pilot.csv"

weather.to_csv(csv_path, index=False)


# 6. Inspeccionar los resultados.
print("\n--- RESULTADOS ---")

print("Registros:", len(weather))
print("Columnas:", weather.columns.tolist())

print("\nPrimeras observaciones:")
print(weather.head())

print("\nValores faltantes:")
print(weather.isna().sum())

print("\nInformación geográfica:")
print("Latitud devuelta:", data["latitude"])
print("Longitud devuelta:", data["longitude"])
print("Elevación:", data.get("elevation"))
print("Zona horaria:", data["timezone"])

print("\nUnidades:")
print(data["hourly_units"])

print("\nArchivos generados:")
print(raw_path)
print(csv_path)

variables = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "precipitation"
]

if weather[variables].isna().any().any():
    raise ValueError(
        "La extracción contiene variables meteorológicas "
        "con valores faltantes."
    )
