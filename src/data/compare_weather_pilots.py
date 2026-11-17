
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"

# Dataset original de enero.
enero = pd.read_csv(
    PROCESSED / "weather_fwi_daily_pilot.csv",
    parse_dates=["date"]
)

# Dataset ampliado.
historial = pd.read_csv(
    PROCESSED / "weather_fwi_spinup_pilot.csv",
    parse_dates=["date"]
)

# Seleccionar enero de 2023.
historial_enero = historial[
    historial["date"].dt.to_period("M")
    == pd.Period("2023-01")
].copy()

# Ordenar y normalizar los índices.
enero = enero.sort_values("date").reset_index(drop=True)
historial_enero = (
    historial_enero.sort_values("date")
    .reset_index(drop=True)
)

print("--- COMPARACIÓN DE DATASETS ---")
print("Registros originales:", len(enero))
print("Registros del historial:", len(historial_enero))

# Comprobar que los datos coincidan.
pd.testing.assert_frame_equal(
    enero,
    historial_enero,
    check_exact=False,
    rtol=1e-10,
    atol=1e-10
)

print("\nVALIDACIÓN EXITOSA")
print("Los datos diarios de enero coinciden.")

