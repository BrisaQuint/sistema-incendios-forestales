
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

import json
import time

import pandas as pd


# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "data/processed/weather_grid_larioja.csv"

OUTPUT = ROOT / "data/processed/weather_locations_larioja.csv"

UNIQUE_OUTPUT = ROOT / "data/processed/weather_locations_unique.csv"

API_URL = "https://archive-api.open-meteo.com/v1/archive"

BATCH_SIZE = 10


# --------------------------------------------------
# CONSULTA A OPEN-METEO
# --------------------------------------------------

def request_locations(batch):
    """Consultar las ubicaciones meteorológicas de un lote."""

    params = {
        "latitude": ",".join(
            str(value) for value in batch["center_lat"]
        ),
        "longitude": ",".join(
            str(value) for value in batch["center_lon"]
        ),
        "start_date": "2023-01-01",
        "end_date": "2023-01-01",
        "hourly": "temperature_2m",
        "models": "era5",
        "cell_selection": "nearest",
        "elevation": ",".join(["nan"] * len(batch)),
        "timezone": "America/Argentina/La_Rioja",
    }

    url = API_URL + "?" + urlencode(params)

    # Reintentos limitados para errores temporales.
    for attempt in range(3):

        try:
            with urlopen(url, timeout=60) as response:
                return json.load(response)

        except HTTPError as error:

            # Mostrar el motivo exacto de un error 400.
            if error.code == 400:

                details = error.read().decode(
                    "utf-8",
                    errors="replace"
                )

                raise ValueError(
                    "Open-Meteo rechazó la solicitud:\n"
                    f"{details}"
                ) from error

            # Otros errores HTTP no recuperables.
            if error.code not in (
                429, 500, 502, 503, 504
            ):
                raise

            # Agotar los reintentos.
            if attempt == 2:
                raise

            time.sleep(5 * (attempt + 1))

        except (URLError, TimeoutError):

            if attempt == 2:
                raise

            time.sleep(5 * (attempt + 1))


# --------------------------------------------------
# INVENTARIO METEOROLÓGICO
# --------------------------------------------------

def main():

    # Leer el inventario geográfico.
    grid = pd.read_csv(INPUT)

    required = {
        "cell_id",
        "center_lat",
        "center_lon",
        "center_inside",
    }

    # Verificar columnas necesarias.
    if not required.issubset(grid.columns):
        raise ValueError(
            "El inventario geográfico está incompleto."
        )

    # Verificar identificadores únicos.
    if grid["cell_id"].duplicated().any():
        raise ValueError(
            "Existen identificadores geométricos duplicados."
        )

    records = []

    # Consultar ubicaciones en lotes.
    for start in range(0, len(grid), BATCH_SIZE):

        batch = grid.iloc[
            start:start + BATCH_SIZE
        ].reset_index(drop=True)

        response = request_locations(batch)

        # Normalizar la respuesta.
        if isinstance(response, dict):
            response = [response]

        # Comprobar la cantidad de ubicaciones.
        if len(response) != len(batch):
            raise ValueError(
                "La API devolvió una cantidad inesperada "
                "de ubicaciones."
            )

        # Registrar las coordenadas efectivas.
        for index, location in enumerate(response):

            original = batch.iloc[index]

            # Detectar errores individuales.
            if location.get("error"):
                raise ValueError(
                    location.get(
                        "reason",
                        "Error desconocido de Open-Meteo."
                    )
                )

            lat = location["latitude"]
            lon = location["longitude"]

            records.append({
                "cell_id": original["cell_id"],
                "requested_lat": original["center_lat"],
                "requested_lon": original["center_lon"],
                "center_inside": original["center_inside"],
                "weather_lat": lat,
                "weather_lon": lon,
                "weather_elevation": location.get(
                    "elevation"
                ),
                "timezone": location.get(
                    "timezone"
                ),
            })

        print(
            "Ubicaciones consultadas: "
            f"{len(records)}/{len(grid)}"
        )

        # Intervalo entre solicitudes.
        time.sleep(2)

    # --------------------------------------------------
    # PROCESAR RESULTADOS
    # --------------------------------------------------

    locations = pd.DataFrame(records)

    # Verificar que se procesaron todas las celdas.
    if len(locations) != len(grid):
        raise ValueError(
            "No se procesaron todas las ubicaciones."
        )

    # Crear identificadores a partir de las
    # coordenadas meteorológicas efectivas.
    locations["weather_id"] = (
        locations["weather_lat"].map(
            lambda value: f"{value:.5f}"
        )
        + "_"
        + locations["weather_lon"].map(
            lambda value: f"{value:.5f}"
        )
    )

    # Identificar ubicaciones meteorológicas únicas.
    unique = locations.drop_duplicates(
        subset=["weather_id"]
    ).copy()

    # --------------------------------------------------
    # GUARDAR INVENTARIOS
    # --------------------------------------------------

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    locations.to_csv(
        OUTPUT,
        index=False
    )

    unique.to_csv(
        UNIQUE_OUTPUT,
        index=False
    )

    # --------------------------------------------------
    # MOSTRAR RESULTADOS
    # --------------------------------------------------

    print("\n--- INVENTARIO METEOROLÓGICO ---")

    print(
        "Celdas geométricas:",
        len(grid)
    )

    print(
        "Ubicaciones meteorológicas distintas:",
        len(unique)
    )

    print(
        "Ubicaciones repetidas:",
        len(locations) - len(unique)
    )

    print("\nArchivos generados:")

    print(OUTPUT)
    print(UNIQUE_OUTPUT)


if __name__ == "__main__":
    main()
