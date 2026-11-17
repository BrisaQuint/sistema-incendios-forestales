
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

import argparse
import json
import time

import pandas as pd


# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

INVENTORY = (
    ROOT / "data/processed/weather_locations_unique.csv"
)

OUTPUT_DIR = ROOT / "data/raw/weather/provincial"

API_URL = "https://archive-api.open-meteo.com/v1/archive"

YEARS = range(2020, 2026)

BATCH_SIZE = 5

VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "precipitation",
]

TIMEZONE = "America/Argentina/La_Rioja"


# --------------------------------------------------
# SOLICITUD HTTP
# --------------------------------------------------

def request_weather(batch, year):

    # El día adicional permite calcular la lluvia
    # de las 24 horas previas al primer mediodía.
    start_date = f"{year - 1}-12-31"

    params = {
        "latitude": ",".join(
            batch["weather_lat"].astype(str)
        ),
        "longitude": ",".join(
            batch["weather_lon"].astype(str)
        ),
        "start_date": start_date,
        "end_date": f"{year}-12-31",
        "hourly": ",".join(VARIABLES),
        "models": "era5",
        "cell_selection": "nearest",
        "elevation": ",".join(
            ["nan"] * len(batch)
        ),
        "timezone": TIMEZONE,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    url = API_URL + "?" + urlencode(params)

    for attempt in range(3):

        try:
            with urlopen(url, timeout=180) as response:
                result = json.load(response)

            if isinstance(result, dict):
                result = [result]

            if len(result) != len(batch):
                raise ValueError(
                    "La API devolvió una cantidad "
                    "inesperada de ubicaciones."
                )

            return result

        except HTTPError as error:

            if error.code not in (
                429, 500, 502, 503, 504
            ):
                details = error.read().decode(
                    "utf-8",
                    errors="replace"
                )

                raise RuntimeError(
                    f"Error HTTP {error.code}:\n"
                    f"{details}"
                ) from error

            if error.code == 429:
                raise RuntimeError(
                    "Open-Meteo indicó que se alcanzó "
                    "un límite de solicitudes. "
                    "Detener la descarga y reanudar "
                    "cuando el servicio lo permita."
                ) from error

            if attempt == 2:
                raise

            time.sleep(10 * (attempt + 1))

        except (URLError, TimeoutError):

            if attempt == 2:
                raise

            time.sleep(10 * (attempt + 1))


# --------------------------------------------------
# RUTAS Y VALIDACIÓN
# --------------------------------------------------

def get_paths(weather_id, year):

    folder = OUTPUT_DIR / str(year)

    safe_id = weather_id.replace(
        "-", "m"
    ).replace(".", "p")

    base = folder / f"weather_{safe_id}_{year}"

    return (
        base.with_suffix(".csv"),
        base.with_suffix(".json")
    )


def expected_times(year):

    """Generar las fechas horarias esperadas para cada año."""

    start = f"{year - 1}-12-31"

    return pd.date_range(
        start=start,
        end=f"{year}-12-31 23:00",
        freq="h"
    )


def validate_weather(weather, year):

    required = ["time", *VARIABLES]

    if not set(required).issubset(
        weather.columns
    ):
        raise ValueError(
            "Faltan columnas meteorológicas."
        )

    times = pd.to_datetime(
        weather["time"],
        errors="raise"
    )

    expected = expected_times(year)

    if not times.reset_index(
        drop=True
    ).equals(
        pd.Series(expected)
    ):
        raise ValueError(
            f"Serie horaria incompleta o "
            f"desordenada para {year}."
        )

    if weather[VARIABLES].isna().any().any():
        raise ValueError(
            "Se encontraron valores "
            "meteorológicos faltantes."
        )

    if not weather[
        "relative_humidity_2m"
    ].between(0, 100).all():
        raise ValueError(
            "Humedad relativa fuera de rango."
        )

    if (
        weather["wind_speed_10m"] < 0
    ).any():
        raise ValueError(
            "Velocidad del viento negativa."
        )

    if (
        weather["precipitation"] < 0
    ).any():
        raise ValueError(
            "Precipitación negativa."
        )


def existing_file_is_valid(
    csv_path,
    json_path,
    year,
    weather_id
):

    if not (
        csv_path.exists()
        and json_path.exists()
    ):
        return False

    try:
        metadata = json.loads(
            json_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            metadata.get("weather_id")
            != weather_id
            or metadata.get("year")
            != year
        ):
            return False

        weather = pd.read_csv(csv_path)

        validate_weather(weather, year)

        return True

    except (
        ValueError,
        OSError,
        KeyError,
        json.JSONDecodeError
    ):
        return False


# --------------------------------------------------
# GUARDADO
# --------------------------------------------------

def save_weather(
    weather,
    metadata,
    csv_path,
    json_path
):

    csv_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Guardado temporal: evita aceptar archivos
    # incompletos si el proceso se interrumpe.
    temp_csv = csv_path.with_suffix(
        ".csv.tmp"
    )

    temp_json = json_path.with_suffix(
        ".json.tmp"
    )

    weather.to_csv(
        temp_csv,
        index=False
    )

    temp_json.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temp_csv.replace(csv_path)
    temp_json.replace(json_path)


# --------------------------------------------------
# DESCARGA PROVINCIAL
# --------------------------------------------------

def download_year(locations, year):

    pending = []

    for _, location in locations.iterrows():

        weather_id = str(
            location["weather_id"]
        )

        csv_path, json_path = get_paths(
            weather_id,
            year
        )

        if existing_file_is_valid(
            csv_path,
            json_path,
            year,
            weather_id
        ):
            continue

        pending.append(location)

    print(
        f"\nAño {year}: "
        f"{len(pending)} ubicaciones pendientes."
    )

    completed = 0

    for start in range(
        0,
        len(pending),
        BATCH_SIZE
    ):

        batch = pd.DataFrame(
            pending[
                start:start + BATCH_SIZE
            ]
        ).reset_index(drop=True)

        responses = request_weather(
            batch,
            year
        )

        for index, response in enumerate(
            responses
        ):

            location = batch.iloc[index]

            weather_id = str(
                location["weather_id"]
            )

            if response.get("error"):
                raise RuntimeError(
                    response.get(
                        "reason",
                        "Error desconocido."
                    )
                )

            # Verificar que las coordenadas
            # devueltas correspondan al inventario.
            lat_diff = abs(
                response["latitude"]
                - location["weather_lat"]
            )

            lon_diff = abs(
                response["longitude"]
                - location["weather_lon"]
            )

            if (
                lat_diff > 0.01
                or lon_diff > 0.01
            ):
                raise ValueError(
                    "La ubicación meteorológica "
                    "cambió respecto del inventario: "
                    f"{weather_id}. "
                    "Revisar antes de continuar."
                )

            if (
                response.get("timezone")
                != TIMEZONE
            ):
                raise ValueError(
                    "Zona horaria inesperada."
                )

            units = response.get(
                "hourly_units",
                {}
            )

            expected_units = {
                "temperature_2m": "°C",
                "relative_humidity_2m": "%",
                "wind_speed_10m": "km/h",
                "precipitation": "mm",
            }

            for variable, unit in (
                expected_units.items()
            ):
                if units.get(variable) != unit:
                    raise ValueError(
                        f"Unidad inesperada "
                        f"para {variable}."
                    )

            weather = pd.DataFrame(
                response["hourly"]
            )

            validate_weather(
                weather,
                year
            )

            csv_path, json_path = get_paths(
                weather_id,
                year
            )

            metadata = {
                "weather_id": weather_id,
                "year": year,
                "model": "era5",
                "cell_selection": "nearest",
                "elevation_adjustment": False,
                "requested_lat": float(
                    location["weather_lat"]
                ),
                "requested_lon": float(
                    location["weather_lon"]
                ),
                "returned_lat": response[
                    "latitude"
                ],
                "returned_lon": response[
                    "longitude"
                ],
                "returned_elevation": (
                    response.get("elevation")
                ),
                "timezone": response[
                    "timezone"
                ],
                "units": units,
                "start_date": f"{year - 1}-12-31",
                "end_date": f"{year}-12-31",
                "source": API_URL,
            }

            save_weather(
                weather,
                metadata,
                csv_path,
                json_path
            )

            completed += 1

        print(
            f"Año {year}: "
            f"{completed}/{len(pending)} "
            "ubicaciones descargadas."
        )

        time.sleep(3)


# --------------------------------------------------
# EJECUCIÓN
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
        choices=YEARS,
        help=(
            "Descargar únicamente "
            "el año indicado."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Limitar la cantidad de "
            "ubicaciones procesadas."
        )
    )

    args = parser.parse_args()

    locations = pd.read_csv(
        INVENTORY
    )

    required = {
        "weather_id",
        "weather_lat",
        "weather_lon",
    }

    if not required.issubset(
        locations.columns
    ):
        raise ValueError(
            "El inventario meteorológico "
            "está incompleto."
        )

    if locations["weather_id"].duplicated().any():
        raise ValueError(
            "El inventario contiene "
            "ubicaciones duplicadas."
        )

    if len(locations) != 169:
        raise ValueError(
            "Se esperaban 169 ubicaciones. "
            "Revisar el inventario."
        )

    if (
        args.limit is not None
        and args.limit < 1
    ):
        parser.error(
            "--limit debe ser mayor que cero."
        )

    if args.limit is not None:
        locations = locations.head(
            args.limit
        )

    selected_years = (
        [args.year]
        if args.year is not None
        else YEARS
    )

    print(
        "Ubicaciones seleccionadas:",
        len(locations)
    )

    for year in selected_years:
        download_year(
            locations,
            year
        )

    print(
        "\nDescarga solicitada finalizada."
    )


if __name__ == "__main__":
    main()
