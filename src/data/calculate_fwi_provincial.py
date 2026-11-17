from pathlib import Path

import pandas as pd

from cffdrs.fwi import (
    fine_fuel_moisture_code,
    duff_moisture_code,
    drought_code,
    initial_spread_index,
    buildup_index,
    fire_weather_index,
)


ROOT = Path(__file__).resolve().parents[2]

INPUT_DIR = ROOT / "data/processed/weather"
OUTPUT_DIR = ROOT / "data/processed/fwi"

INVENTORY = ROOT / "data/processed/weather_locations_unique.csv"

YEARS = range(2020, 2026)

INITIAL_FFMC = 85.0
INITIAL_DMC = 6.0
INITIAL_DC = 15.0


def drought_code_safe(
    dc_yda,
    temp,
    rh,
    prec,
    lat,
    mon,
    lat_adjust=True,
):
    """
    Calcular DC evitando que cffdrs evalúe innecesariamente
    la fórmula de humectación cuando prec <= 2.8 mm.

    Para prec > 2.8 mm se utiliza directamente la implementación
    original de cffdrs.
    """

    if prec <= 2.8:
        # Factores mensuales utilizados por cffdrs.
        fl01 = [
            -1.6, -1.6, -1.6, 0.9, 3.8, 5.8,
            6.4, 5.0, 2.4, 0.4, -1.6, -1.6,
        ]

        fl02 = [
            6.4, 5.0, 2.4, 0.4, -1.6, -1.6,
            -1.6, -1.6, -1.6, 0.9, 3.8, 5.8,
        ]

        temp = max(temp, -2.8)

        factor = fl01[mon - 1]

        if lat_adjust:
            if lat <= -20:
                factor = fl02[mon - 1]
            elif lat <= 20:
                factor = 1.4

        pe = (0.36 * (temp + 2.8) + factor) / 2.0
        pe = max(pe, 0.0)

        return max(dc_yda + pe, 0.0)

    return drought_code(
        dc_yda=dc_yda,
        temp=temp,
        rh=rh,
        prec=prec,
        lat=lat,
        mon=mon,
        lat_adjust=lat_adjust,
    )


def load_weather():
    """Cargar y comprobar las entradas meteorológicas diarias."""

    parts = []

    for year in YEARS:
        path = INPUT_DIR / f"weather_fwi_daily_{year}.csv.gz"

        if not path.is_file():
            raise FileNotFoundError(
                f"Falta el año {year}: {path}"
            )

        part = pd.read_csv(
            path,
            parse_dates=["date"],
            dtype={"weather_id": str},
        )

        expected_days = (
            pd.Timestamp(f"{year + 1}-01-01")
            - pd.Timestamp(f"{year}-01-01")
        ).days

        expected_rows = 169 * expected_days

        if len(part) != expected_rows:
            raise ValueError(
                f"Cantidad de registros incorrecta para {year}: "
                f"{len(part)} en lugar de {expected_rows}."
            )

        parts.append(part)

    weather = pd.concat(
        parts,
        ignore_index=True,
    )

    if weather.isna().any().any():
        raise ValueError(
            "Existen datos meteorológicos faltantes."
        )

    if weather.duplicated(
        ["weather_id", "date"]
    ).any():
        raise ValueError(
            "Existen registros meteorológicos duplicados."
        )

    return weather.sort_values(
        ["weather_id", "date"]
    ).reset_index(drop=True)


def calculate_location(data, latitude):
    """Calcular los seis componentes del FWI secuencialmente."""

    ffmc = INITIAL_FFMC
    dmc = INITIAL_DMC
    dc = INITIAL_DC

    results = []

    for row in data.itertuples(index=False):
        date = row.date

        temp = float(row.temperature_2m)
        rh = float(row.relative_humidity_2m)
        wind = float(row.wind_speed_10m)
        rain = float(row.rain_24h)

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
            lat=latitude,
            mon=int(date.month),
            lat_adjust=True,
        )

        dc = drought_code_safe(
            dc_yda=dc,
            temp=temp,
            rh=rh,
            prec=rain,
            lat=latitude,
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

        results.append(
            {
                "weather_id": row.weather_id,
                "date": date,
                "ffmc": ffmc,
                "dmc": dmc,
                "dc": dc,
                "isi": isi,
                "bui": bui,
                "fwi": fwi,
            }
        )

    return pd.DataFrame(results)


def main():
    locations = pd.read_csv(
        INVENTORY,
        dtype={"weather_id": str},
    )

    if (
        len(locations) != 169
        or locations["weather_id"].duplicated().any()
        or locations["weather_lat"].isna().any()
    ):
        raise ValueError(
            "El inventario meteorológico no es válido."
        )

    weather = load_weather()

    # Los registros meteorológicos diarios representan
    # las condiciones locales de las 12:00 utilizadas por FWI.
    expected_dates = pd.date_range(
        "2020-01-01 12:00:00",
        "2025-12-31 12:00:00",
        freq="D",
    )

    expected_ids = set(
        locations["weather_id"]
    )

    actual_ids = set(
        weather["weather_id"]
    )

    if actual_ids != expected_ids:
        raise ValueError(
            "Las ubicaciones no coinciden con el inventario."
        )

    # Comprobar continuidad temporal de cada ubicación
    # antes de iniciar el cálculo secuencial.
    for weather_id, group in weather.groupby(
        "weather_id"
    ):
        actual_dates = pd.DatetimeIndex(
            group["date"]
        )

        if not actual_dates.equals(expected_dates):
            raise ValueError(
                f"Serie diaria incompleta: {weather_id}"
            )

    print(
        "Datos completos. Iniciando cálculo "
        "provincial del FWI."
    )

    results = []

    for index, location in enumerate(
        locations.itertuples(index=False),
        start=1,
    ):
        data = weather[
            weather["weather_id"]
            == location.weather_id
        ].sort_values("date")

        calculated = calculate_location(
            data,
            latitude=float(location.weather_lat),
        )

        results.append(calculated)

        if index % 20 == 0 or index == 169:
            print(
                f"Ubicaciones calculadas: {index}/169"
            )

    provincial = pd.concat(
        results,
        ignore_index=True,
    )

    indices = [
        "ffmc",
        "dmc",
        "dc",
        "isi",
        "bui",
        "fwi",
    ]

    expected_total = 169 * len(expected_dates)

    if len(provincial) != expected_total:
        raise ValueError(
            "Cantidad total de resultados FWI incorrecta: "
            f"{len(provincial)} en lugar de {expected_total}."
        )

    if provincial[indices].isna().any().any():
        raise ValueError(
            "Los resultados FWI contienen valores faltantes."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for year in YEARS:
        annual = provincial[
            provincial["date"].dt.year == year
        ].copy()

        expected_days = (
            pd.Timestamp(f"{year + 1}-01-01")
            - pd.Timestamp(f"{year}-01-01")
        ).days

        expected_rows = 169 * expected_days

        if len(annual) != expected_rows:
            raise ValueError(
                f"Cantidad FWI incorrecta para {year}: "
                f"{len(annual)} en lugar de {expected_rows}."
            )

        output = (
            OUTPUT_DIR
            / f"fwi_larioja_{year}.csv.gz"
        )

        annual.to_csv(
            output,
            index=False,
            compression="gzip",
        )

        print(
            f"{year}: {len(annual)} registros "
            f"guardados en {output.name}"
        )

    print("\nCálculo provincial completado.")


if __name__ == "__main__":
    main()