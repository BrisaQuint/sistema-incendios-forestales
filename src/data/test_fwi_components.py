
from cffdrs.fwi import (
    fine_fuel_moisture_code,
    duff_moisture_code,
    drought_code_safe,
    initial_spread_index,
    buildup_index,
    fire_weather_index,
)

# Condiciones meteorológicas de ejemplo.
temp = 20.0
rh = 60.0
wind = 15.0
rain = 0.0

# Ubicación y mes del experimento.
latitude = -29.5
month = 1

# Estados iniciales convencionales.
ffmc_initial = 85.0
dmc_initial = 6.0
dc_initial = 15.0

# Calcular los tres códigos de humedad.
ffmc = fine_fuel_moisture_code(
    ffmc_yda=ffmc_initial,
    temp=temp,
    rh=rh,
    ws=wind,
    prec=rain
)

dmc = duff_moisture_code(
    dmc_yda=dmc_initial,
    temp=temp,
    rh=rh,
    prec=rain,
    lat=latitude,
    mon=month,
    lat_adjust=True
)

dc = drought_code_safe(
    dc_yda=dc_initial,
    temp=temp,
    rh=rh,
    prec=rain,
    lat=latitude,
    mon=month,
    lat_adjust=True
)

# Calcular los índices derivados.
isi = initial_spread_index(
    ffmc=ffmc,
    ws=wind
)

bui = buildup_index(
    dmc=dmc,
    dc=dc
)

fwi = fire_weather_index(
    isi=isi,
    bui=bui
)

print("--- PRUEBA DE COMPONENTES FWI ---")
print(f"FFMC: {ffmc:.4f}")
print(f"DMC:  {dmc:.4f}")
print(f"DC:   {dc:.4f}")
print(f"ISI:  {isi:.4f}")
print(f"BUI:  {bui:.4f}")
print(f"FWI:  {fwi:.4f}")
