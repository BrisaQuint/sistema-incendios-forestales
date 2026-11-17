
from pathlib import Path
import argparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "weather"
PROCESSED_DIR = ROOT / "data" / "processed"


def prepare_daily(
    input_path,
    output_path,
    start_date,
    end_date,
    verbose=True
):
    # Leer las observaciones horarias.
    weather = pd.read_csv(
        input_path,
        parse_dates=["time"]
    ).sort_values("time")

    variables = [
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "precipitation"
    ]

    # Comprobar la calidad de los datos.
    if weather[variables].isna().any().any():
        raise ValueError("Hay variables meteorológicas incompletas.")

    if weather["time"].duplicated().any():
        raise ValueError("Existen fechas horarias duplicadas.")

    # Comprobar continuidad de toda la serie.
    expected = pd.date_range(
        weather["time"].min(),
        weather["time"].max(),
        freq="h"
    )

    if not weather["time"].reset_index(drop=True).equals(
        pd.Series(expected)
    ):
        raise ValueError("La serie horaria tiene interrupciones.")

    weather = weather.set_index("time")

    # La precipitación horaria corresponde a la hora anterior.
    weather["rain_24h"] = (
        weather["precipitation"]
        .rolling(window=24, min_periods=24)
        .sum()
    )

    # Seleccionar las observaciones de las 12:00.
    daily = weather.loc[
        weather.index.hour == 12,
        [
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "rain_24h"
        ]
    ].copy()

    # Seleccionar el período solicitado.
    daily = daily.loc[start_date:end_date]

    if daily.isna().any().any():
        raise ValueError("El dataset diario tiene valores faltantes.")

    # Verificar que exista un registro por cada día.
    expected_days = pd.date_range(
        start_date,
        end_date,
        freq="D"
    )

    if not daily.index.normalize().equals(expected_days):
        raise ValueError("Faltan días en el dataset procesado.")

    daily.index.name = "date"
    daily = daily.reset_index()

    if output_path is not None:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )
        daily.to_csv(
            output_path,
            index=False
        )

    if verbose:
        print("\n--- ENTRADAS DIARIAS FWI ---")
        print("Registros:", len(daily))
        print("Primera fecha:", daily["date"].min())
        print("Última fecha:", daily["date"].max())

        print("\nPrimeros cinco días:")
        print(daily.head().to_string(index=False))

        print("\nValores faltantes:")
        print(daily.isna().sum())

        if output_path is not None:
            print("\nArchivo generado:", output_path)

    return daily


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)

    args = parser.parse_args()

    prepare_daily(
        RAW_DIR / args.input,
        PROCESSED_DIR / args.output,
        args.start,
        args.end
    )
