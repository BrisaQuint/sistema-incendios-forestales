from pathlib import Path
from pyogrio import set_gdal_config_options

import geopandas as gpd
import pandas as pd


# Raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Dataset original NASA FIRMS
FIRMS_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "firms"
    / "fire_archive_SV-C2_809555.csv"
)

# Límites provinciales oficiales del IGN
PROVINCES_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "boundaries"
    / "provincia.geojson"
)


print("Raíz del proyecto:", PROJECT_ROOT)
print("NASA FIRMS encontrado:", FIRMS_PATH.exists())
print("GeoJSON IGN encontrado:", PROVINCES_PATH.exists())

print("\n--- Cargando NASA FIRMS ---")

firms = pd.read_csv(FIRMS_PATH)

print("Dataset cargado correctamente.")
print("Cantidad de filas:", len(firms))
print("Cantidad de columnas:", len(firms.columns))

print("\nColumnas disponibles:")
print(firms.columns.tolist())

print("\nPrimeros 5 registros:")
print(firms.head())

print("\n--- Validación básica FIRMS ---")

print("\nTipos de datos:")
print(firms.dtypes)

print("\nValores nulos por columna:")
print(firms.isna().sum())

print("\nValores de type:")
print(firms["type"].value_counts().sort_index())

print("\nValores de confidence:")
print(firms["confidence"].value_counts())

print("\nValores de satellite:")
print(firms["satellite"].value_counts())

print("\nValores de instrument:")
print(firms["instrument"].value_counts())

firms["acq_date"] = pd.to_datetime(firms["acq_date"])

print("\n--- Cobertura temporal ---")
print("Fecha inicial:", firms["acq_date"].min())
print("Fecha final:", firms["acq_date"].max())

print("\nRegistros por año:")
print(
    firms["acq_date"]
    .dt.year
    .value_counts()
    .sort_index()
)

print("\n--- Cargando límites provinciales IGN ---")

# Configurar GDAL para permitir geometrías GeoJSON grandes.
set_gdal_config_options({
    "OGR_GEOJSON_MAX_OBJ_SIZE": "0"
})

# Leer los límites provinciales.
provinces = gpd.read_file(
    PROVINCES_PATH,
    engine="pyogrio"
)

print("Cantidad de jurisdicciones:", len(provinces))

print("\nColumnas del GeoJSON:")
print(provinces.columns.tolist())

print("\nSistema de coordenadas:")
print(provinces.crs)

print("\nProvincias disponibles:")
print(provinces["nam"].sort_values().to_string(index=False))

la_rioja = provinces[provinces["nam"] == "La Rioja"].copy()

print("\n--- Selección de La Rioja ---")
print("Geometrías encontradas:", len(la_rioja))
print("Tipo de geometría:", la_rioja.geometry.geom_type.tolist())
print("CRS:", la_rioja.crs)
print("Límites geográficos:", la_rioja.total_bounds)


print("\n--- Filtrado geoespacial FIRMS ---")

# Comprobar que encontramos exactamente una geometría.
if len(la_rioja) != 1:
    raise ValueError(
        "Se esperaba una única geometría para La Rioja."
    )

# Verificar la validez de la geometría provincial.
if not la_rioja.geometry.is_valid.all():
    raise ValueError(
        "La geometría de La Rioja no es válida."
    )

# Crear puntos geográficos utilizando longitud y latitud.
firms_geo = gpd.GeoDataFrame(
    firms,
    geometry=gpd.points_from_xy(
        firms["longitude"],
        firms["latitude"]
    ),
    crs="EPSG:4326"
)

# Asegurar que ambos datasets utilizan el mismo CRS.
la_rioja = la_rioja.to_crs(firms_geo.crs)

# Filtrar los puntos contenidos en La Rioja.
firms_larioja = firms_geo[
    firms_geo.geometry.within(la_rioja.geometry.iloc[0])
].copy()

print("Detecciones originales:", len(firms_geo))
print("Detecciones en La Rioja:", len(firms_larioja))

print("\nDetecciones por año:")
print(
    firms_larioja["acq_date"]
    .dt.year
    .value_counts()
    .sort_index()
)

print("\nDistribución por tipo:")
print(
    firms_larioja["type"]
    .value_counts()
    .sort_index()
)


print("\n--- Preparación del dataset procesado ---")

# Crear la carpeta de salida si todavía no existe.
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Conservar todas las detecciones provinciales.
firms_larioja.drop(
    columns="geometry"
).to_csv(
    OUTPUT_DIR / "firms_larioja_todos_2020_2025.csv",
    index=False
)

# Seleccionar presuntos incendios de vegetación.
firms_vegetacion = firms_larioja[
    firms_larioja["type"] == 0
].copy()

# Exportar sin la geometría auxiliar.
firms_vegetacion.drop(
    columns="geometry"
).to_csv(
    OUTPUT_DIR / "firms_larioja_vegetacion_2020_2025.csv",
    index=False
)

print("Detecciones provinciales:", len(firms_larioja))
print("Presuntos incendios de vegetación:", len(firms_vegetacion))

print("\nRegistros de vegetación por año:")
print(
    firms_vegetacion["acq_date"]
    .dt.year
    .value_counts()
    .sort_index()
)

print("\nArchivos generados en:", OUTPUT_DIR)
