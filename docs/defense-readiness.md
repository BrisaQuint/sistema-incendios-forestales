# Consolidación documental para la defensa de FireWatch

Verificación sobre `4f6c9309a94d27db957e847fd2eee0df28bb9329`. Documento operativo, fuera del seguimiento BMAD: no cambia PRD, estados, épicas ni alcance funcional. Conserva las diferencias respecto de los compromisos originales. Solo se leyeron artefactos existentes y SQLite con `mode=ro`; no se ejecutaron pipelines, análisis del producto, agentes ni llamadas OpenAI.

## FR-7: conversión horaria y distancias

`src/data/integrate_firms_fwi.py` reconstruye UTC desde `acq_date` y `acq_time` HHMM, convierte con `America/Argentina/La_Rioja`, toma el día local y lo asocia al FWI de las 12:00. Asigna el punto meteorológico más cercano por Haversine, radio 6371,0088 km, usando `weather_lat`/`weather_lon`, no centros geométricos de grilla.

Evidencia: `data/processed/firms_fwi_larioja_2021_2025.csv.gz`, 10.956 filas, todas `type=0`; SHA-256 `236362b619bb7eb51d22f28dcd57ab0284c789e77be465fc6cf0be04934eef24`. Lectura de sus columnas existentes:

- Cero diferencias al reconstruir UTC y al comparar fecha/hora local y offset con la conversión de zona.
- Cero diferencias entre el día local de adquisición y el día FWI asociado, siempre a las 12:00.
- Media de `weather_distance_km`: 10,234303747696842 km; máximo: 20,943611175365522 km. Redondeados a tres decimales: **10,234 km y 20,944 km**.
- Agrupar las detecciones por `weather_id` y día FWI reproduce exactamente los `firms_count` de las 2.286 celdas-día con detección del snapshot `2026-10-08-2`.

El CSV de detecciones no es un payload del snapshot: se identifica su propia huella y se comprueba la correspondencia de conteos, sin atribuirle la validación criptográfica del bundle. No se recalcularon distancias desde coordenadas; se verificaron los agregados de la columna persistida y el algoritmo fuente.

Aclaración metodológica mínima respaldada: «Las adquisiciones FIRMS se convirtieron de UTC a hora local de La Rioja. En las 10.956 detecciones integradas de 2021–2025, la distancia al punto meteorológico asociado tuvo media 10,234 km y máximo 20,944 km. Son estadísticas del conjunto, no distancias de la ubicación o detección seleccionada. La asociación al FWI de las 12:00 del mismo día es histórica y descriptiva, no causal ni predictiva; una detección previa puede asociarse a condiciones posteriores».

Esta aclaración queda documentada aquí; incorporarla al dashboard requiere aprobación y un cambio de texto frontend. El snapshot/API actuales no exponen distancias individuales ni horas individuales: siguen no disponibles en esa interfaz. No corresponde sustituirlas por la media o el máximo.

## FR-8: evidencia mensual y anual

No se encontró un resumen mensual/anual persistido en el directorio principal `data/processed`. La evidencia reproducible reside en `weather_daily` y `monthly_fwi_reference` del SQLite validado. Se verificó mediante consulta de solo lectura:

```sql
SELECT d.date, d.fwi - r.median_fwi AS anomaly
FROM weather_daily d
JOIN monthly_fwi_reference r
  ON r.weather_id = d.weather_id
 AND r.month = CAST(substr(d.date, 6, 2) AS INTEGER)
WHERE d.date BETWEEN '2021-01-01' AND '2025-12-31'
  AND d.firms_count > 0;
```

Se agruparon esas filas por mes calendario y, por separado, por año; se aplicó `statistics.median` a las anomalías individuales. Cada celda-día pesa una vez, sin ponderar por cantidad de detecciones; no se toma la mediana de medianas ni se recalcula la referencia dentro de cada año. 2020 queda excluido.

| Mes | Celdas-día con detección | Anomalía mediana FWI (6 decimales) |
|---|---:|---:|
| Enero | 140 | +2,529521 |
| Febrero | 70 | +0,348863 |
| Marzo | 96 | +4,524667 |
| Abril | 117 | +1,494635 |
| Mayo | 112 | +0,364282 |
| Junio | 134 | +1,971998 |
| Julio | 175 | +1,787071 |
| Agosto | 314 | +3,256543 |
| Septiembre | 345 | +3,526448 |
| Octubre | 311 | +4,728122 |
| Noviembre | 319 | +7,428897 |
| Diciembre | 153 | +7,310658 |

| Año | Celdas-día con detección | Anomalía mediana FWI (6 decimales) |
|---|---:|---:|
| 2021 | 485 | +3,032046 |
| 2022 | 532 | +4,504661 |
| 2023 | 507 | +2,641981 |
| 2024 | 385 | +4,270014 |
| 2025 | 377 | +0,765294 |

Ambas particiones suman 2.286 celdas-día. Se confirma la afirmación descriptiva de mediana positiva en los 12 meses y los cinco años; no significa que cada celda-día tenga anomalía positiva ni constituye desempeño predictivo.

**Diferencia pendiente de producto:** el PRD FR-8 incluye esa afirmación mensual/anual, pero el endpoint y el dashboard entregan solo agregados globales. Este documento cubre su evidencia académica; no se declara implementado el desglose interactivo. Una frase metodológica sería un ajuste pequeño de texto. Un desglose servido por API implica cálculo agrupado, contrato, generación de tipos, presentación y pruebas: es acotado, pero no un cambio exclusivamente documental. No se implementa sin aprobación ni se fijan cifras nuevas en componentes.

## SM-2: procedencia de los 14 completados determinísticos

La auditoría local conserva 15 `completed`: 14 tienen exactamente `run_queued`, `run_started`, `analysis_core_result_persisted`, `run_completed`, sin intervenciones, explicación ni metadatos de proveedor. El otro es la aceptación real `73356254-ffa8-4397-b208-938579eee91d`, con tres roles y 11 eventos.

Se contrastaron `created_at` UTC y `git log --format='%h %aI %s'`:

- `604c949` incorpora el flujo MAS a la API, fecha de commit `2026-10-08T03:20:39-03:00` (06:20:39 UTC).
- Cinco registros se crearon antes de ese commit, entre 05:29:13 y 06:10:57 UTC: `6e589d90-41b6-474f-bff7-a096dca6324b`, `e348f4d4-c695-44ce-8dfa-6b6da1bfb494`, `8483f336-5139-4f62-94ac-5f1df117a3e2`, `399dea47-05da-4358-933d-95f7954c0f13`, `dd05c8b1-5e7b-4a1e-96c4-04953642084e`.
- Nueve se crearon después, entre 06:21:09 y 06:32:40 UTC: `b1e34412-1ed6-44a4-9101-09504745283b`, `4dd82101-e285-4493-8b83-fbb505145df1`, `23c8e196-5c78-430d-9e42-7c967cc96b72`, `9bd3dd39-0dec-46d8-9c62-69f1c4bf388c`, `2b7de282-a846-446b-b6c8-4dfee9c58103`, `c538567c-6b29-441b-90eb-1f5c1c898f30`, `bc61a587-926a-4a3d-b8df-8bc75eac82ce`, `450ca6d7-6c9d-4663-9529-451025652b01`, `7053a599-5dea-4a8e-8a2a-bf80cf7ca475`.

`git show 2078842:src/sistema_incendios_forestales/api/app.py` demuestra un camino histórico que llama `audit_store.execute` sin colaboración. `git show 604c949:src/sistema_incendios_forestales/api/app.py` y el código actual incorporan `collaborate=collaborate` y el orquestador. El almacén también permite ejecución determinística directa sin colaboración.

**Límite de atribución:** la auditoría no conserva versión del runtime, PID ni origen HTTP/directo por ejecución. La fecha de commit no prueba qué código estaba cargado en un proceso ni cuándo existió código sin confirmar. Los cinco primeros son temporalmente anteriores a la publicación del MAS y compatibles con el flujo previo; no se prueba la versión exacta. Para los nueve posteriores no se puede distinguir entre proceso antiguo, invocación directa u otro origen con la evidencia disponible. No se atribuyen todos a una versión anterior ni se presentan como evidencia de una regresión actual demostrada.

SM-2, formulado sobre todos los completados disponibles, sigue sin cumplirse para esa población histórica. El análisis real de aceptación y las pruebas del flujo actual respaldan el camino multiagente actual, sin corregir retrospectivamente los 14 registros. No se alteran, reclasifican, borran ni completan artificialmente.

## Validación Python/R: alcance y precisión

Fuentes: `src/data/validate_fwi_reference.R`, `src/data/compare_fwi_reference.py`, `data/processed/fwi_initialization_experiment.csv` y `data/processed/fwi_reference_r.csv`. La comparación selecciona el piloto a latitud -29,5°, escenario `A_convencional`, iniciado el 2022-07-01 con FFMC=85, DMC=6 y DC=15; compara solo los 31 días de enero de 2023. No equivale a la validación de toda la cobertura ni del spin-up provincial.

La lectura comparada de los CSV existentes, sin volver a ejecutar R ni calcular FWI, reproduce diferencias absolutas máximas: FFMC 4,2633e-14; DMC 2,8422e-13; DC 5,6843e-13; ISI 4,6185e-14; BUI 4,2633e-13; FWI 4,9738e-14. Todas inferiores a la tolerancia `1e-4` del script; todas se imprimen como `0,00000000` a ocho decimales. El «máximo observado 0» del PRD se interpreta como resultado redondeado, no igualdad binaria exacta. No se modifica silenciosamente ese texto ni se afirma calibración ecológica local.

## Operación y diferencias conservadas

El [README](../README.md) documenta el arranque en el equipo de defensa, digest aprobado, replay del análisis real sin ejecutar otro, proveedor mock explícito para consulta y limitaciones del procedimiento. El snapshot y la auditoría están fuera de Git; instalar dependencias puede requerir conexión previa. No se realizó un nuevo ensayo de arranque ni Ctrl+C en esta consolidación.

La decisión aprobada de conservar íntegramente auditoría sustituye operativamente la retención de 30 días descrita en AD-11 y NFR-8; esos compromisos originales permanecen en arquitectura y épicas como referencia, con esta diferencia explícita. No existe purga/compactación ni variable de retención implementada. La rotación de logs no purga análisis.

No se modifican estados BMAD ni se afirma conformidad integral WCAG. No hay evidencia nueva de lector de pantalla. Ninguna diferencia aquí registrada se resuelve inventando datos ni ejecutando otra llamada real a OpenAI.
