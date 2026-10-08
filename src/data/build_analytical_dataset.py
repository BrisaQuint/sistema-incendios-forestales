from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

FWI_DIR = ROOT / "data/processed/fwi"

FIRMS_FWI_PATH = (
    ROOT
    / "data/processed/firms_fwi_larioja_2021_2025.csv.gz"
)

OUTPUT_PATH = (
    ROOT
    / "data/processed/analytical_larioja_2021_2025.csv.gz"
)

YEARS = range(2021, 2026)


def load_fwi():
    """Cargar la base completa de celdas-día FWI."""

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
            "Existen celdas-día FWI duplicadas."
        )

    if fwi.isna().any().any():
        raise ValueError(
            "El FWI contiene valores faltantes."
        )

    return fwi


def load_firms_counts():
    """
    Agregar las detecciones FIRMS por weather_id y día FWI.
    """

    firms = pd.read_csv(
        FIRMS_FWI_PATH,
        parse_dates=["fwi_datetime"],
        dtype={"weather_id": str},
    )

    if firms.empty:
        raise ValueError(
            "El dataset FIRMS-FWI está vacío."
        )

    counts = (
        firms
        .groupby(
            ["weather_id", "fwi_datetime"]
        )
        .size()
        .rename("firms_count")
        .reset_index()
    )

    counts = counts.rename(
        columns={"fwi_datetime": "date"}
    )

    return counts


def main():
    print(
        "Construyendo dataset analítico celda-día."
    )

    fwi = load_fwi()
    firms_counts = load_firms_counts()

    analytical = fwi.merge(
        firms_counts,
        on=["weather_id", "date"],
        how="left",
        validate="one_to_one",
    )

    analytical["firms_count"] = (
        analytical["firms_count"]
        .fillna(0)
        .astype(int)
    )

    analytical["firms_detected"] = (
        analytical["firms_count"] > 0
    ).astype(int)

    expected_days = (
        pd.Timestamp("2026-01-01")
        - pd.Timestamp("2021-01-01")
    ).days

    expected_rows = 169 * expected_days

    if len(analytical) != expected_rows:
        raise ValueError(
            "Cantidad incorrecta de celdas-día: "
            f"{len(analytical)} en lugar de "
            f"{expected_rows}."
        )

    if analytical.duplicated(
        ["weather_id", "date"]
    ).any():
        raise ValueError(
            "El dataset analítico contiene "
            "celdas-día duplicadas."
        )

    if analytical.isna().any().any():
        raise ValueError(
            "El dataset analítico contiene "
            "valores faltantes."
        )

    # Debemos conservar exactamente todas las detecciones
    # FIRMS del período al agregarlas por celda-día.
    expected_detections = 10956

    if analytical["firms_count"].sum() != expected_detections:
        raise ValueError(
            "La cantidad total de detecciones FIRMS "
            "no se conservó correctamente."
        )

    analytical = analytical.sort_values(
        ["weather_id", "date"]
    ).reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    analytical.to_csv(
        OUTPUT_PATH,
        index=False,
        compression="gzip",
    )

    cells_with_detection = int(
        analytical["firms_detected"].sum()
    )

    cells_without_detection = (
        len(analytical)
        - cells_with_detection
    )

    print("\n=== DATASET ANALÍTICO ===")
    print(
        f"Filas totales: {len(analytical)}"
    )
    print(
        "Ubicaciones: "
        f"{analytical['weather_id'].nunique()}"
    )
    print(
        f"Días: {expected_days}"
    )
    print(
        "Detecciones FIRMS conservadas: "
        f"{analytical['firms_count'].sum()}"
    )
    print(
        "Celdas-día con detección: "
        f"{cells_with_detection}"
    )
    print(
        "Celdas-día sin detección: "
        f"{cells_without_detection}"
    )
    print(
        "Máximo de detecciones en una celda-día: "
        f"{analytical['firms_count'].max()}"
    )

    print("\nCeldas-día con detección por año:")
    print(
        analytical[
            analytical["firms_detected"] == 1
        ]
        .groupby(
            analytical["date"].dt.year
        )
        .size()
        .to_string()
    )

    print(
        "\nArchivo generado: "
        f"{OUTPUT_PATH}"
    )

    print(
        "\nDataset analítico completado."
    )


if __name__ == "__main__":
    main()