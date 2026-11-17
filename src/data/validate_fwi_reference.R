
# Validación de referencia: FWI con R
# FireWatch - La Rioja

library(
  cffdrs,
  lib.loc = file.path(
    Sys.getenv("USERPROFILE"),
    "R",
    "library"
  )
)

input_path <- "data/processed/weather_fwi_spinup_pilot.csv"
output_path <- "data/processed/fwi_reference_r.csv"

weather <- read.csv(input_path)
weather$date <- as.Date(substr(weather$date, 1, 10))

# Verificar el dataset original.
stopifnot(nrow(weather) == 215)
stopifnot(!anyNA(weather))
# Verificar la continuidad de las fechas.
expected_dates <- seq(
  as.Date("2022-07-01"),
  as.Date("2023-01-31"),
  by = "day"
)

cat("\n--- DIAGNÓSTICO DE FECHAS ---\n")
cat("Clase:", class(weather$date), "\n")
cat("Primera fecha:", as.character(head(weather$date, 1)), "\n")
cat("Última fecha:", as.character(tail(weather$date, 1)), "\n")
cat("Fechas duplicadas:", sum(duplicated(weather$date)), "\n")
cat("Fechas faltantes:", sum(!expected_dates %in% weather$date), "\n")
cat("Fechas inesperadas:", sum(!weather$date %in% expected_dates), "\n")

stopifnot(
  length(weather$date) == length(expected_dates),
  !anyDuplicated(weather$date),
  all(weather$date == expected_dates)
)
# Preparar las variables que espera cffdrs.
input <- data.frame(
  id = rep("La_Rioja_piloto", nrow(weather)),
  yr = as.integer(format(weather$date, "%Y")),
  mon = as.integer(format(weather$date, "%m")),
  day = as.integer(format(weather$date, "%d")),
  lat = rep(-29.5, nrow(weather)),
  temp = weather$temperature_2m,
  rh = weather$relative_humidity_2m,
  ws = weather$wind_speed_10m,
  prec = weather$rain_24h
)

# Cálculo secuencial con condiciones iniciales
# equivalentes al escenario A de Python.
result <- cffdrs::fwi(
  input = input,
  init = data.frame(
    ffmc = 85,
    dmc = 6,
    dc = 15,
    lat = -29.5
  ),
  batch = TRUE,
  out = "fwi",
  lat.adjust = TRUE,
  uppercase = FALSE
)

# Normalizar los nombres de salida.
names(result) <- tolower(names(result))

components <- c(
  "ffmc", "dmc", "dc",
  "isi", "bui", "fwi"
)

stopifnot(nrow(result) == 215)
stopifnot(all(components %in% names(result)))
stopifnot(!anyNA(result[components]))

# Conservar fechas y componentes.
output <- data.frame(
  date = weather$date,
  result[components]
)

write.csv(
  output,
  output_path,
  row.names = FALSE
)

cat("\n--- VALIDACIÓN DE REFERENCIA R ---\n")
cat("Versión cffdrs:", as.character(packageVersion("cffdrs")), "\n")
cat("Registros:", nrow(output), "\n")
cat("Primer día:", as.character(min(output$date)), "\n")
cat("Último día:", as.character(max(output$date)), "\n")
cat("\nPrimeros resultados:\n")
print(head(output, 3))
cat("\nArchivo:", output_path, "\n")
