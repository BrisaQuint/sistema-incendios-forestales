# Story 2.5 — Operabilidad y ensayo local

Base: Story 2.4 publicada (`3f44077`). Evidencia final de Story 2.5 y Epic 2, con cierre formal aprobado por el usuario. No se modifica la auditoría histórica ni el snapshot. No se ejecuta OpenAI real durante Story 2.5.

## Conservación de auditoría: decisión de alcance aprobada

FireWatch es un prototipo académico: se conservan íntegramente las auditorías y resultados durante el desarrollo y la defensa. No existe purga ni retención temporal de auditoría implementada. Esta decisión del usuario sustituye para Story 2.5 el objetivo anterior de retención temporal y no bloquea el cierre. La rotación de logs operativos es independiente de la auditoría.

`analysis_events_no_delete` y los demás mecanismos de integridad permanecen intactos. No se implementará compactación ni eliminación automática, ni se mantiene como propuesta o pendiente. No se modifica `data/firewatch-audit.sqlite` ni la evidencia histórica de Story 1.9.

## Logging implementado

El punto de entrada local instala `RotatingFileHandler`, sin dependencias nuevas:

- `FIREWATCH_LOG_PATH`: por defecto `data/logs/firewatch.log`.
- `FIREWATCH_LOG_MAX_BYTES`: por defecto 1048576 bytes.
- `FIREWATCH_LOG_BACKUP_COUNT`: por defecto 3 copias, además del archivo actual.
- Límites deben ser enteros positivos; errores no reproducen el valor inválido.

El formato deliberadamente mínimo registra timestamp, nivel y categoría server/application. Omite mensajes libres, argumentos, tracebacks y stack_info; evita registrar prompts o secretos desconocidos, a costa de menor detalle diagnóstico. Los detalles operativos deben correlacionarse con los códigos tipados de API/audit. Las excepciones SQL y de validación del resultado se traducen a mensajes constantes antes de persistirse.

Uvicorn usa `log_config=None`; sus loggers propagan al handler configurado. El handler se cierra al terminar el punto de entrada. La garantía cubre este archivo, no handlers externos preinstalados, invocaciones alternativas de Uvicorn, stdout/stderr, errores previos a configurar logging ni trazas producidas por herramientas externas. Su retención depende del lanzador. No redirigir volcados de entorno, HTTP debug o prompts a logs. No se inspeccionaron valores secretos reales.

## Evidencia histórica reutilizada

ID `73356254-ffa8-4397-b208-938579eee91d`: `docs/bmad/implementation/acceptance-runs/story-1.9-2026-10-09-e2e-attempt-03.json`, contrastado en auditoría previa con SQLite en modo solo lectura. Estado completed; OpenAI gpt-6-luna, sin MockLLM; tres roles completados, revisión aprobada, explicación presente y 11 eventos terminando en run_completed. Replay registrado desde cursor 0 hasta 11. Es evidencia histórica de Story 1.9, no conectividad actual ni una llamada de Story 2.5.

## Ensayos automatizados y alcance

- Suite existente: fallo simulado del proveedor conserva FWI y produce partial; fallo SQL/FWI ausente produce failed; configuración inválida rechazada, migraciones, readiness y worker loopback único.
- `test_restart_then_resume_cursor_without_provider_calls`: dos lifespans TestClient aislados, snapshot/audit temporales; simula pérdida de sesión y reinicio con cursor conservado, con/sin FWI. Exige run_interrupted, terminal correcto, replay exclusivo ordenado y proveedor prohibido durante consultas.
- `tests/test_process_recovery.py`: procesos Python propios con Uvicorn, puertos loopback efímeros y SQLite temporal. Socket SSE real recibe eventos y se desconecta con run activo; se interrumpe únicamente el proceso hijo propio, se reinicia sobre la misma auditoría temporal y se reanuda desde Last-Event-ID. Se comprueban orden sin duplicaciones, run_interrupted, partial con FWI y failed sin FWI, ausencia de explicación y cero llamadas al MockLLM instrumentado. La ejecución activa se prepara determinísticamente: no es una llamada LLM en vuelo.
- Configuración inválida y puerto ocupado por un socket propio producen salida no exitosa. Readiness y PID corresponden al proceso servidor creado; Uvicorn usa un worker. Apagado ordenado mediante should_exit verifica cierre de audit y snapshot, salida cero y posibilidad de volver a enlazar el puerto. No se envían señales al servidor de revisión ni se usa el puerto 8000.
- `test_rotation_and_secret_canaries`: fuerza rotación con 180 bytes y dos copias; mensajes, argumentos y excepción contienen señuelos, ausentes de todos los archivos.
- Configuración de límites inválidos con señuelo; punto de entrada con servidor mock y log temporal.
- Suite completa: 93 passed en 14,41 s. La primera ejecución tuvo 2 fallos de las pruebas nuevas por usar SQLite desde otro hilo; corregidos ejecutando la preparación dentro del portal del lifespan.
- Ensayos iniciales de proceso: 3 passed en 19,96 s. Al ampliar las comprobaciones se detectaron dos problemas del harness: la ruta PID quedaba detrás del fallback SPA y el ejecutable del venv Windows actuaba como intermediario. Se corrigió el orden de la ruta exclusiva de test y se lanzó directamente el intérprete base con las rutas de paquetes del entorno. La comprobación de procesos launch.py no encontró procesos residuales.
- Validación final: `uv run pytest tests/ -q --tb=short`, **96 passed en 34,68 s**, incluidos todos los ensayos de proceso/socket, cierre de ambas SQLite, PID, fallos simulados, rotación y sanitización.
- Después se añadió un señuelo SQL a la prueba existente de fallo determinístico: `tests/test_audit_store.py`, 11 passed en 3,80 s. Confirma que el resultado persistido no incluye el señuelo.
- `git diff --check`: correcto. No se repitió build porque no hubo cambios frontend.

## Estado de aceptación

| Criterio | Estado observado |
|---|---|
| Fallos de proveedor/herramienta y conservación de salidas | Demostrado en pruebas con proveedor y SQLite temporales; no es un ensayo facturable. |
| SSE, cursor y recuperación tras interrupción | Demostrado con socket real, interrupción y reinicio de procesos propios, con/sin FWI; se conserva cursor y no se llama LLM. |
| Arranque, configuración, proceso único, cierre y logs | Cubierto por pruebas de runtime, procesos y logging rotatorio; auditorías conservadas íntegramente según alcance aprobado. |
| Ejecución real y guion de fallo controlado | Evidencia histórica de Story 1.9 reutilizada y guion preparado; no se realizó otra llamada OpenAI. |

## Guion reproducible de defensa

1. En una consola propia, instalar desde lockfiles si fuera necesario; compilar frontend con `npm --prefix frontend run build`. Usar el snapshot existente `2026-10-08-2`; no ejecutar builder sobre la release.
2. Configurar nombres documentados en README: directorio/version/digest aprobado del snapshot, ruta de audit existente y proveedor. Mantener credenciales fuera del historial y no imprimirlas. Iniciar `uv run sistema-incendios-forestales` (127.0.0.1:8000, un worker). Arrancar no autoriza ejecutar análisis.
3. Consultar GET `http://127.0.0.1:8000/api/health/ready` y abrir `http://127.0.0.1:8000/?analysis_id=73356254-ffa8-4397-b208-938579eee91d`. Recupera por GET: no pulsar Ejecutar este día.
4. Consultar GET `/api/analyses/73356254-ffa8-4397-b208-938579eee91d/trace`; inspeccionar eventos reales y resultado. Abrir hallazgos históricos: GET `/api/study/exploratory`.
5. Mostrar fallo controlado mediante `uv run pytest tests/test_trace_api.py tests/test_audit_store.py tests/test_mas_orchestrator.py -q --tb=short`: utiliza temporales y proveedor simulado; identificarlo así, sin presentarlo como fallo de OpenAI real.
6. Mostrar recuperación real aislada mediante `uv run pytest tests/test_process_recovery.py -q --tb=short`. El test administra sus propios procesos y puertos, conserva cursor y muestra partial/failed según FWI. No reutiliza el puerto 8000 ni la auditoría histórica.
7. Apagar con Ctrl+C únicamente la consola de demostración propia y comprobar cierre. No detener el servidor de revisión ni otro proceso. El ensayo automático verifica el cierre ordenado con should_exit, no la entrega de Ctrl+C desde una terminal Windows.

Configuración inválida: revisar nombres y presencia de variables sin imprimir sus valores; comprobar ruta, versión y digest contra manifiesto aprobado, build existente y permisos. No regenerar snapshot ni sustituir auditoría para ocultar un error. Puerto ocupado: inspeccionar propietario con `Get-NetTCPConnection -LocalPort 8000`, sin finalizar procesos; reutilizar servidor autorizado o acordar una ventana de demostración. El punto de entrada fija 8000: no lanzar una segunda instancia contra la misma audit.

## Pendientes

No quedan pendientes de compactación/purga: están fuera del alcance aprobado. La prueba de interrupción usa un run activo preparado y un proveedor simulado, no un request OpenAI en vuelo. No se verificó Ctrl+C en terminal interactiva ni conectividad actual de OpenAI; no son resultados atribuidos a los ensayos automáticos. No hace falta otra llamada OpenAI para reutilizar la evidencia histórica. El procedimiento de defensa está documentado, pero no se ejecutó contra el servidor de revisión ni se cambió su configuración.
