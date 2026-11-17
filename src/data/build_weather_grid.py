
from pathlib import Path

import geopandas as gpd
import pandas as pd
import numpy as np

from shapely.geometry import box, Point
from pyogrio import set_gdal_config_options


ROOT = Path(__file__).resolve().parents[2]

BOUNDARIES = (
    ROOT / "data/raw/boundaries/provincia.geojson"
)

OUTPUT_DIR = ROOT / "data/processed"
GRID_CSV = OUTPUT_DIR / "weather_grid_larioja.csv"
GRID_GEOJSON = OUTPUT_DIR / "weather_grid_larioja.geojson"

RESOLUTION = 0.25


def main():
    # Permitir la lectura del GeoJSON del IGN.
    set_gdal_config_options({
        "OGR_GEOJSON_MAX_OBJ_SIZE": "0"
    })

    provinces = gpd.read_file(BOUNDARIES)

    # Seleccionar La Rioja.
    larioja = provinces[
        provinces["nam"] == "La Rioja"
    ].to_crs("EPSG:4326")

    if len(larioja) != 1:
        raise ValueError(
            "No se encontró una única geometría de La Rioja."
        )

    territory = larioja.geometry.iloc[0]

    if territory.is_empty or not territory.is_valid:
        raise ValueError(
            "La geometría provincial no es válida."
        )

    min_lon, min_lat, max_lon, max_lat = territory.bounds

    # Construir una cuadrícula regular de 0,25°.
    lon_start = (
        np.floor(min_lon / RESOLUTION) * RESOLUTION
    )
    lon_end = (
        np.ceil(max_lon / RESOLUTION) * RESOLUTION
    )

    lat_start = (
        np.floor(min_lat / RESOLUTION) * RESOLUTION
    )
    lat_end = (
        np.ceil(max_lat / RESOLUTION) * RESOLUTION
    )

    longitudes = np.arange(
        lon_start,
        lon_end,
        RESOLUTION
    )

    latitudes = np.arange(
        lat_start,
        lat_end,
        RESOLUTION
    )

    records = []

    for lat in latitudes:
        for lon in longitudes:

            cell = box(
                lon,
                lat,
                lon + RESOLUTION,
                lat + RESOLUTION
            )

            # Conservar celdas con intersección territorial.
            if not cell.intersects(territory):
                continue

            center_lon = lon + RESOLUTION / 2
            center_lat = lat + RESOLUTION / 2

            center = Point(center_lon, center_lat)

            center_inside = territory.covers(center)

            records.append({
                "cell_id": (
                    f"ERA5_{lat:+08.3f}_{lon:+09.3f}"
                ),
                "center_lat": round(center_lat, 4),
                "center_lon": round(center_lon, 4),
                "center_inside": center_inside,
                "geometry": cell
            })

    grid = gpd.GeoDataFrame(
        records,
        geometry="geometry",
        crs="EPSG:4326"
    )

    if grid.empty:
        raise ValueError(
            "No se encontraron celdas para La Rioja."
        )

    if grid["cell_id"].duplicated().any():
        raise ValueError(
            "Se encontraron identificadores duplicados."
        )

    grid = grid.sort_values(
        ["center_lat", "center_lon"]
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Inventario tabular para adquisición meteorológica.
    grid.drop(columns="geometry").to_csv(
        GRID_CSV,
        index=False
    )

    # Geometrías para visualización y análisis espacial.
    grid.to_file(
        GRID_GEOJSON,
        driver="GeoJSON"
    )

    print("\n--- CUADRÍCULA DE LA RIOJA ---")
    print("Resolución:", RESOLUTION, "grados")
    print("Celdas que intersectan:", len(grid))

    print(
        "Celdas con centro dentro:",
        int(grid["center_inside"].sum())
    )

    print(
        "Celdas periféricas:",
        int((~grid["center_inside"]).sum())
    )

    print("\nPrimeras cinco celdas:")
    print(
        grid.drop(columns="geometry")
        .head()
        .to_string(index=False)
    )

    print("\nArchivos generados:")
    print(GRID_CSV)
    print(GRID_GEOJSON)


if __name__ == "__main__":
    main()
