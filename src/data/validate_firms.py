
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"

todos = pd.read_csv(
    PROCESSED / "firms_larioja_todos_2020_2025.csv"
)

vegetacion = pd.read_csv(
    PROCESSED / "firms_larioja_vegetacion_2020_2025.csv"
)

# Verificar las cantidades obtenidas.
assert len(todos) == 12439
assert len(vegetacion) == 12437

# Verificar las categorías conservadas.
assert vegetacion["type"].eq(0).all()

# Verificar coordenadas geográficas.
assert vegetacion["latitude"].between(-90, 90).all()
assert vegetacion["longitude"].between(-180, 180).all()

# Verificar el período histórico.
fechas = pd.to_datetime(
    vegetacion["acq_date"],
    errors="coerce"
)

assert fechas.notna().all()
assert fechas.min() >= pd.Timestamp("2020-01-01")
assert fechas.max() <= pd.Timestamp("2025-12-31")

# Comprobar la estructura de los datos.
assert len(vegetacion.columns) == 15
assert not vegetacion.isna().any().any()

print("VALIDACIÓN COMPLETADA")
print("Detecciones provinciales:", len(todos))
print("Detecciones de vegetación:", len(vegetacion))
print("Columnas:", len(vegetacion.columns))
print("Valores faltantes:", vegetacion.isna().sum().sum())
print("Período:", fechas.min().date(), fechas.max().date())
