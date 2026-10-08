
from pathlib import Path
import argparse
import json

import pandas as pd

from prepare_fwi_daily import prepare_daily


ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = ROOT / "data/raw/weather/provincial"
PROCESSED_DIR = ROOT / "data/processed/weather"

INVENTORY = (
    ROOT / "data/processed/weather_locations_unique.csv"
)


def consolidate_year(year):
    """Consolidar las entradas diarias de un año."""

    year_dir = RAW_DIR / str(year)

    if not year_dir.is_dir():
        raise FileNotFoundError(
            f"No existe el directorio: {year_dir}"
        )

    locations = pd.read_csv(
        INVENTORY,
        dtype={"weather_id": str}
    )

    if locations["weather_id"].duplicated().any():
        raise ValueError(
            "El inventario tiene ubicaciones duplicadas."
        )

    expected_ids = set(
        locations["weather_id"]
    )

    if len(expected_ids) != 169:
        raise ValueError(
            "Se esperaban 169 ubicaciones meteorológicas."
        )

    # Indexar los metadatos descargados.
    metadata_by_id = {}

    for json_path in year_dir.glob("weather_*.json"):

        metadata = json.loads(
            json_path.read_text(
                encoding="utf-8"
            )
        )

        weather_id = metadata.get("weather_id")

        if metadata.get("year") != year:
            raise ValueError(
                f"Año incorrecto en {json_path.name}"
            )

        if weather_id in metadata_by_id:
            raise ValueError(
                f"Metadatos duplicados: {weather_id}"
            )

        csv_path = json_path.with_suffix(".csv")

        if not csv_path.is_file():
            raise FileNotFoundError(
                f"Falta el archivo: {csv_path}"
            )

        metadata_by_id[weather_id] = (
            metadata,
            csv_path
        )

    downloaded_ids = set(metadata_by_id)

    missing = expected_ids - downloaded_ids
    unexpected = downloaded_ids - expected_ids

    if missing or unexpected:
        raise ValueError(
            "El inventario no coincide con los "
            "archivos descargados.\n"
            f"Faltantes: {len(missing)}\n"
            f"Inesperados: {len(unexpected)}"
        )

    # Procesar cada ubicación individualmente.
    daily_parts = []

    for index, location in enumerate(
        locations.itertuples(index=False),
        start=1
    ):

        weather_id = location.weather_id

        metadata, csv_path = (
            metadata_by_id[weather_id]
        )

        # Confirmar la configuración de adquisición.
        if (
            metadata.get("model") != "era5"
            or metadata.get("timezone")
            != "America/Argentina/La_Rioja"
        ):
            raise ValueError(
                "Configuración meteorológica inesperada "
                f"para {weather_id}"
            )

        daily = prepare_daily(
            input_path=csv_path,
            output_path=None,
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
            verbose=False
        )

        daily.insert(
            0,
            "weather_id",
            weather_id
        )

        daily_parts.append(daily)

        if index % 20 == 0 or index == len(locations):
            print(
                f"Ubicaciones procesadas: "
                f"{index}/{len(locations)}"
            )

    # Consolidar únicamente las entradas diarias.
    consolidated = pd.concat(
        daily_parts,
        ignore_index=True
    )

    expected_days = (
        pd.Timestamp(f"{year + 1}-01-01")
        - pd.Timestamp(f"{year}-01-01")
    ).days

    expected_rows = (
        len(locations) * expected_days
    )

    if len(consolidated) != expected_rows:
        raise ValueError(
            "Cantidad inesperada de registros diarios."
        )

    if consolidated.duplicated(
        subset=["weather_id", "date"]
    ).any():
        raise ValueError(
            "Existen registros diarios duplicados."
        )

    if consolidated.isna().any().any():
        raise ValueError(
            "Existen valores faltantes."
        )

    consolidated = consolidated.sort_values(
        ["weather_id", "date"]
    ).reset_index(drop=True)

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = (
        PROCESSED_DIR
        / f"weather_fwi_daily_{year}.csv.gz"
    )

    # Guardar primero en un archivo temporal.
    temporary_path = (
        PROCESSED_DIR
        / f"weather_fwi_daily_{year}.tmp.csv.gz"
    )

    consolidated.to_csv(
        temporary_path,
        index=False,
        compression="gzip"
    )

    # Verificar el archivo comprimido.
    saved = pd.read_csv(
        temporary_path,
        compression="gzip"
    )

    if len(saved) != expected_rows:
        raise ValueError(
            "La verificación del archivo falló."
        )

    if saved.isna().any().any():
        raise ValueError(
            "El archivo guardado contiene "
            "valores faltantes."
        )

    temporary_path.replace(output_path)

    print("\n--- CONSOLIDACIÓN COMPLETADA ---")
    print("Año:", year)
    print("Ubicaciones:", len(locations))
    print("Días:", expected_days)
    print("Registros diarios:", len(consolidated))
    print("Archivo:", output_path)
    print(
        "Tamaño comprimido (MB):",
        round(
            output_path.stat().st_size / 1_000_000,
            2
        )
    )

    print(
        "\nLos archivos horarios originales "
        "no fueron eliminados."
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
        required=True,
        choices=range(2020, 2026)
    )

    args = parser.parse_args()

    consolidate_year(args.year)


if __name__ == "__main__":
    main()
