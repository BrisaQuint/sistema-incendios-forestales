
from pathlib import Path
from itertools import product

import pandas as pd

from cffdrs.fwi import (
    fine_fuel_moisture_code,
    duff_moisture_code,
    drought_code_safe,
    initial_spread_index,
    buildup_index,
    fire_weather_index,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data/processed/weather_fwi_spinup_pilot.csv"
OUTPUT = ROOT / "data/processed/fwi_initialization_experiment.csv"

LATITUDE = -29.5

# Estados iniciales hipotéticos.
INITIAL_STATES = {
    "A_convencional": (85.0, 6.0, 15.0),
    "B_alternativa": (80.0, 20.0, 100.0),
    "C_alternativa": (90.0, 40.0, 200.0),
}

# Distintas duraciones del período previo.
START_DATES = [
    "2022-07-01",
    "2022-10-01",
    "2022-12-01",
]

weather = pd.read_csv(INPUT, parse_dates=["date"])
weather = weather.sort_values("date").reset_index(drop=True)

assert len(weather) == 215
assert not weather.isna().any().any()

results = []

# Ejecutar las nueve combinaciones.
for (scenario, initial), start in product(
    INITIAL_STATES.items(),
    START_DATES
):
    ffmc, dmc, dc = initial

    subset = weather[
        weather["date"] >= pd.Timestamp(start)
    ]

    for row in subset.itertuples(index=False):
        date = row.date
        temp = float(row.temperature_2m)
        rh = float(row.relative_humidity_2m)
        wind = float(row.wind_speed_10m)
        rain = float(row.rain_24h)

        # Actualizar los estados secuencialmente.
        ffmc = fine_fuel_moisture_code(
            ffmc_yda=ffmc,
            temp=temp,
            rh=rh,
            ws=wind,
            prec=rain,
        )

        dmc = duff_moisture_code(
            dmc_yda=dmc,
            temp=temp,
            rh=rh,
            prec=rain,
            lat=LATITUDE,
            mon=int(date.month),
            lat_adjust=True,
        )

        dc = drought_code_safe(
            dc_yda=dc,
            temp=temp,
            rh=rh,
            prec=rain,
            lat=LATITUDE,
            mon=int(date.month),
            lat_adjust=True,
        )

        isi = initial_spread_index(
            ffmc=ffmc,
            ws=wind,
        )

        bui = buildup_index(
            dmc=dmc,
            dc=dc,
        )

        fwi = fire_weather_index(
            isi=isi,
            bui=bui,
        )

        results.append({
            "date": date,
            "scenario": scenario,
            "start_date": start,
            "ffmc": ffmc,
            "dmc": dmc,
            "dc": dc,
            "isi": isi,
            "bui": bui,
            "fwi": fwi,
        })

results = pd.DataFrame(results)

# Analizar exclusivamente enero de 2023.
january = results[
    (results["date"] >= "2023-01-01")
    & (results["date"] < "2023-02-01")
].copy()

# Comprobar que tenemos 31 días por ejecución.
counts = january.groupby(
    ["scenario", "start_date"]
).size()

assert len(counts) == 9
assert counts.eq(31).all()
assert january["fwi"].notna().all()

# Conservar todos los resultados de enero.
january.to_csv(OUTPUT, index=False)

print("\n--- EXPERIMENTO DE INICIALIZACIÓN FWI ---")
print("Ejecuciones:", len(counts))
print("Registros de enero:", len(january))

summary = january.groupby(
    ["scenario", "start_date"]
).agg(
    fwi_mean=("fwi", "mean"),
    fwi_max=("fwi", "max"),
    dc_final=("dc", "last"),
)

print("\nResumen de las nueve ejecuciones:")
print(summary.round(3).to_string())

# Medir diferencias entre inicializaciones
# para cada duración del período previo.
print("\n--- SENSIBILIDAD A LA INICIALIZACIÓN ---")

for start, group in january.groupby("start_date"):
    comparison = group.pivot(
        index="date",
        columns="scenario",
        values="fwi",
    )

    daily_range = (
        comparison.max(axis=1)
        - comparison.min(axis=1)
    )

    print(f"\nInicio: {start}")
    print(
        "Diferencia máxima entre escenarios:",
        round(daily_range.max(), 4)
    )
    print(
        "Diferencia media entre escenarios:",
        round(daily_range.mean(), 4)
    )

print("\nArchivo generado:", OUTPUT)
