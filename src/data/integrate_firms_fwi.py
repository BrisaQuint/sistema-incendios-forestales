from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

FIRMS_PATH = (
    ROOT
    / "data/processed/firms_larioja_vegetacion_2020_2025.csv"
)

WEATHER_LOCATIONS_PATH = (
    ROOT
    / "data/processed/weather_locations_unique.csv"
)

FWI_DIR = ROOT / "data/processed/fwi"

OUTPUT_PATH = (
    ROOT
    / "data/processed/firms_fwi_larioja_2021_2025.csv.gz"
)

YEARS = range(2021, 2026)

EARTH_RADIUS_KM = 6371.0088


def haversine_distances(
    latitude,
    longitude,
    target_latitudes,
    target_longitudes,
):
    """
    Calcular distancia geodésica aproximada mediante Haversine
    desde un punto FIRMS hacia todas las ubicaciones ERA5.
    """

    lat1 = np.radians(latitude)
    lon1 = np.radians(longitude)

    lat2 = np.radians(target_latitudes)
    lon2 = np.radians(target_longitudes)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2.0) ** 2
    )

    c = 2.0 * np.arctan2(
        np.sqrt(a),
        np.sqrt(1.0 - a),
    )

    return EARTH_RADIUS_KM * c


def load_fwi():
    """Cargar el FWI correspondiente al período principal."""

    parts = []

    for year in YEARS:
        path = FWI_DIR / f"fwi_larioja_{year}.csv.gz"

        if not path.is_file():
            raise FileNotFoundError(
                f"Falta el archivo FWI: {path}"
            )

        part = pd.read_csv(
            path,
            parse_dates=["date"],
            dtype={"weather_id": str},
        )

        parts.append(part)

    fwi = pd.concat(
        parts,
        ignore_index=True,
    )

    if fwi.duplicated(
        ["weather_id", "date"]
    ).any():
        raise ValueError(
            "El FWI contiene weather_id/fecha duplicados."
        )

    if fwi.isna().any().any():
        raise ValueError(
            "El FWI contiene valores faltantes."
        )

    return fwi


def prepare_firms():
    """Cargar FIRMS y construir fecha/hora UTC y local."""

    firms = pd.read_csv(
        FIRMS_PATH,
        dtype={
            "satellite": str,
            "instrument": str,
            "confidence": str,
            "daynight": str,
        },
    )

    if firms.empty:
        raise ValueError(
            "El archivo FIRMS está vacío."
        )

    if firms[
        ["latitude", "longitude", "acq_date", "acq_time"]
    ].isna().any().any():
        raise ValueError(
            "FIRMS contiene datos espacio-temporales faltantes."
        )

    # El archivo utilizado ya corresponde a type=0.
    if not (firms["type"] == 0).all():
        raise ValueError(
            "Existen registros FIRMS distintos de type=0."
        )

    firms["acq_date"] = pd.to_datetime(
        firms["acq_date"],
        format="%Y-%m-%d",
    )

    # Período principal del estudio.
    firms = firms[
        firms["acq_date"].dt.year.isin(YEARS)
    ].copy()

    # FIRMS almacena acq_time como HHMM en UTC.
    time_text = (
        firms["acq_time"]
        .astype(int)
        .astype(str)
        .str.zfill(4)
    )

    datetime_text = (
        firms["acq_date"].dt.strftime("%Y-%m-%d")
        + " "
        + time_text.str[:2]
        + ":"
        + time_text.str[2:]
    )

    firms["acq_datetime_utc"] = pd.to_datetime(
        datetime_text,
        format="%Y-%m-%d %H:%M",
        utc=True,
    )

    # Argentina continental utiliza UTC-3 durante
    # todo el período analizado.
    firms["acq_datetime_local"] = (
        firms["acq_datetime_utc"]
        .dt.tz_convert("America/Argentina/La_Rioja")
    )

    # El FWI diario representa las condiciones de las 12:00 locales.
    local_dates = (
        firms["acq_datetime_local"]
        .dt.tz_localize(None)
        .dt.normalize()
    )

    firms["fwi_datetime"] = (
        local_dates
        + pd.Timedelta(hours=12)
    )

    return firms.reset_index(drop=True)


def assign_nearest_weather_location(
    firms,
    locations,
):
    """
    Asignar a cada detección FIRMS la ubicación meteorológica
    ERA5 más cercana y conservar la distancia de asociación.
    """

    target_latitudes = (
        locations["weather_lat"]
        .astype(float)
        .to_numpy()
    )

    target_longitudes = (
        locations["weather_lon"]
        .astype(float)
        .to_numpy()
    )

    weather_ids = (
        locations["weather_id"]
        .astype(str)
        .to_numpy()
    )

    assigned_ids = []
    assigned_distances = []

    for row in firms.itertuples(index=False):
        distances = haversine_distances(
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            target_latitudes=target_latitudes,
            target_longitudes=target_longitudes,
        )

        nearest_index = int(
            np.argmin(distances)
        )

        assigned_ids.append(
            weather_ids[nearest_index]
        )

        assigned_distances.append(
            float(distances[nearest_index])
        )

    result = firms.copy()

    result["weather_id"] = assigned_ids
    result["weather_distance_km"] = assigned_distances

    return result


def main():
    print(
        "Iniciando integración FIRMS-FWI."
    )

    locations = pd.read_csv(
        WEATHER_LOCATIONS_PATH,
        dtype={"weather_id": str},
    )

    if (
        len(locations) != 169
        or locations["weather_id"].duplicated().any()
        or locations[
            ["weather_lat", "weather_lon"]
        ].isna().any().any()
    ):
        raise ValueError(
            "El inventario meteorológico no es válido."
        )

    firms = prepare_firms()

    print(
        f"Detecciones FIRMS 2021-2025: {len(firms)}"
    )

    firms = assign_nearest_weather_location(
        firms,
        locations,
    )

    fwi = load_fwi()

    integrated = firms.merge(
        fwi,
        left_on=[
            "weather_id",
            "fwi_datetime",
        ],
        right_on=[
            "weather_id",
            "date",
        ],
        how="left",
        validate="many_to_one",
    )

    fwi_columns = [
        "ffmc",
        "dmc",
        "dc",
        "isi",
        "bui",
        "fwi",
    ]

    missing_fwi = (
        integrated[fwi_columns]
        .isna()
        .any(axis=1)
        .sum()
    )

    if missing_fwi != 0:
        raise ValueError(
            f"{missing_fwi} detecciones FIRMS "
            "no pudieron asociarse con FWI."
        )

    if len(integrated) != len(firms):
        raise ValueError(
            "La integración modificó la cantidad "
            "de detecciones FIRMS."
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    integrated.to_csv(
        OUTPUT_PATH,
        index=False,
        compression="gzip",
    )

    print("\n=== RESULTADO ===")
    print(
        f"Detecciones integradas: {len(integrated)}"
    )
    print(
        "Ubicaciones FWI utilizadas: "
        f"{integrated['weather_id'].nunique()}"
    )
    print(
        "Distancia mínima (km): "
        f"{integrated['weather_distance_km'].min():.3f}"
    )
    print(
        "Distancia media (km): "
        f"{integrated['weather_distance_km'].mean():.3f}"
    )
    print(
        "Distancia mediana (km): "
        f"{integrated['weather_distance_km'].median():.3f}"
    )
    print(
        "Distancia máxima (km): "
        f"{integrated['weather_distance_km'].max():.3f}"
    )

    print("\nDetecciones por año:")
    print(
        integrated[
            "acq_datetime_local"
        ]
        .dt.year
        .value_counts()
        .sort_index()
        .to_string()
    )

    print(
        "\nArchivo generado: "
        f"{OUTPUT_PATH}"
    )

    print(
        "\nIntegración FIRMS-FWI completada."
    )


if __name__ == "__main__":
    main()