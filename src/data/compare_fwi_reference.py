
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"

python = pd.read_csv(
    DATA / "fwi_initialization_experiment.csv",
    parse_dates=["date"]
)

reference = pd.read_csv(
    DATA / "fwi_reference_r.csv",
    parse_dates=["date"]
)

# Seleccionar exclusivamente el escenario
# convencional iniciado en julio.
python = python[
    (python["scenario"] == "A_convencional")
    & (python["start_date"] == "2022-07-01")
].copy()

# Comparar enero, ya que nuestro experimento
# de Python guardó únicamente ese mes.
reference = reference[
    reference["date"].dt.to_period("M")
    == pd.Period("2023-01")
].copy()

components = [
    "ffmc", "dmc", "dc",
    "isi", "bui", "fwi"
]

python["date"] = python["date"].dt.normalize()
reference["date"] = reference["date"].dt.normalize()

comparison = python[
    ["date"] + components
].merge(
    reference[["date"] + components],
    on="date",
    suffixes=("_python", "_r"),
    validate="one_to_one"
)

assert len(comparison) == 31

print("\n--- COMPARACIÓN PYTHON VS R ---")
print("Días comparados:", len(comparison))

tolerance = 1e-4
all_passed = True

for component in components:
    difference = (
        comparison[f"{component}_python"]
        - comparison[f"{component}_r"]
    ).abs()

    maximum = difference.max()
    passed = maximum <= tolerance

    if not passed:
        all_passed = False

    print(
        f"{component.upper():5} "
        f"Diferencia máxima: {maximum:.8f} "
        f"{'OK' if passed else 'REVISAR'}"
    )

if all_passed:
    print("\nVALIDACIÓN NUMÉRICA EXITOSA")
else:
    print("\nEXISTEN DISCREPANCIAS")
    print("No considerar validado el cálculo.")
