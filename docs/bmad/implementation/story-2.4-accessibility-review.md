# Story 2.4 — Revisión de accesibilidad y adaptación

Fecha: 2026-10-10. Base examinada: `a077a48d59a8912a4d5a7899f69e6b9acab21c71`, más las correcciones locales de Story 2.4 sin commit.

## Alcance y referencia

Frontend: `frontend/src/App.tsx` y `frontend/src/style.css`. Referencias: Story 2.4 de `epics.md`, NFR-9, UX-DR11/12 y UJ-1 de `EXPERIENCE.md` aprobado. Se conserva una superficie continua, detalles progresivos, contexto del resultado y límites científicos. Referencia normativa: https://www.w3.org/TR/WCAG22/.

Revisión estática y compilación, complementadas por las verificaciones manuales en navegador confirmadas por el usuario al aprobar el cierre. No se realizaron pruebas con lector de pantalla. No se ejecutaron análisis reales ni llamadas OpenAI durante este trabajo. No se declara conformidad integral WCAG 2.2 AA.

## Hallazgos y correcciones

| Criterio | Evidencia y actuación | Estado |
|---|---|---|
| 4.1.3 Mensajes de estado | La finalización solo aparecía en texto ordinario y dentro de la traza contraída. Se añadió una región persistente, `role=status`, `aria-live=polite`, `aria-atomic=true`, fuera de desplegables. Su texto depende del estado global, no de la secuencia SSE. Se retiraron anuncios duplicados de errores/parcial y el segundo mensaje de error de cobertura. | Corregido en código; audición pendiente |
| 3.3.1, 3.3.2, 3.3.3 | Fechas y ubicación se relacionan con la ayuda de cobertura mediante `aria-describedby`; fechas inválidas usan `aria-invalid`. Se conserva la selección y el mensaje de corrección. | Asociación estática comprobada; interacción pendiente |
| 1.3.1 Información y relaciones | Tablas conservan encabezados de columna y ahora identifican variable/agente con `th scope=row`; valores y unidades no cambian. | Estructura comprobada; lectura asistida pendiente |
| UJ-1: Agente/Tarea/Estado/Resultado-Evidencia | Faltaban tarea y referencias en el resumen de traza. Se muestran la última tarea registrada y las referencias existentes por agente. Ausencias se declaran, sin inventar eventos. Sigue siendo un resumen por rol: no es un listado detallado de cada intervención. | Brecha mínima corregida; revisar con traza existente que tenga revisión de agente |
| 2.4.7, 2.4.11 | Se conserva contorno azul de 3 px y se elimina `overflow:hidden` del resultado, que podía recortar el contorno de los resúmenes próximos al borde. | Revisión manual de foco satisfactoria en los escenarios revisados |
| 1.4.4, 1.4.10 | Se permite envolver comparación, métricas, títulos y resúmenes estrechos; navegación diaria también envuelve. Selectores tienen contenedor reducible. Tablas mantienen desplazamiento local y región enfocable. | Revisión manual satisfactoria a 320 px y zoom 200%/400%; tablas, gráficos, traza y textos legibles |
| 2.5.8 | Botón secundario Reintentar con altura mínima de 24 px. | Regla comprobada; geometría renderizada pendiente |
| 1.4.3, 1.4.11 | Contrastes calculados sobre pares CSS: secundario/blanco 7,21:1; blanco/verde del botón 7,13:1; error/fondo 10,92:1; foco/blanco 5,98:1; borde/blanco 3,65:1. No se cambiaron colores. | Pares comprobados; todos los estados renderizados pendientes |
| 1.1.1, 1.4.1 | Gráficos históricos decorativos con `aria-hidden`; medianas, etiquetas, cantidades, porcentajes y denominadores permanecen en texto. FWI no recibe categorías de riesgo ni depende solo del color. | Evidencia estática conservada; lectura real pendiente |
| 2.1.1, 2.1.2, 2.4.3, 4.1.2 | Controles y desplegables nativos; no se añade orden de tabulación positivo ni desplazamiento automático de foco. | Tab/Shift+Tab, Enter/Espacio y desplegables comprobados manualmente; semántica con lector de pantalla pendiente |

## Validaciones automatizadas

- `npm run build`: correcto (TypeScript y Vite).
- `uv run pytest tests/ -q --tb=short`: 88 passed en 15,03 s.
- `git diff --check`: correcto.
- No se añadieron dependencias ni pruebas que solo replican el JSX. La suite existente no verifica anuncios de lectores de pantalla ni geometría del navegador.

## Verificaciones manuales confirmadas por el usuario

- Navegación con Tab y Shift+Tab y activación de controles con Enter y Espacio.
- Foco y desplegables: revisión satisfactoria.
- Pantalla de 320 px y zoom 200%/400%: revisión satisfactoria; tablas, gráficos, traza y textos legibles en los escenarios revisados.
- Estados parciales y resultados persistidos: presentación visual comprobada.

Estos resultados fueron comunicados por el usuario; no constituyen pruebas ejecutadas por el agente. No se proporcionaron versiones de navegador, capturas ni tecnología de asistencia. No se generalizan a escenarios no revisados.

## Verificaciones pendientes y limitaciones

1. Revisar específicamente el foco al deshabilitar el botón de ejecución en un entorno simulado; este caso no fue confirmado por separado.
2. NVDA u otra tecnología de asistencia: nombres, estados expandidos, encabezados de fila/columna, unidades, tarea y referencias; comprobar símbolos decorativos de los resúmenes.
3. Estados simulados o resultados existentes: ejecución, completado, parcial, error y reconexión. Confirmar un anuncio terminal comprensible y ausencia de anuncios por cada evento SSE.
4. Fechas invertidas, fuera de cobertura y día fuera del período: asociación del error, sugerencia de corrección y conservación del contexto.
5. Registrar dimensiones iniciales de ventana, navegador y versión de las verificaciones de zoom ya aceptadas; no se presume cobertura de todas las combinaciones de contenido y estados.
6. Medir contraste renderizado, área de controles, espaciado de texto y todos los fondos/estados. Registrar navegador, versión, sistema operativo, lector de pantalla, viewport y capturas cuando corresponda.

## Conclusión de cierre

Story 2.4 aceptada para cierre por el usuario, con correcciones mínimas y revisión manual de teclado, foco y adaptación satisfactoria en los escenarios indicados. La compilación no demuestra accesibilidad. La lectura con NVDA u otra tecnología de asistencia y los anuncios ARIA no fueron verificados empíricamente. Se conservan los pendientes específicos arriba registrados y no se afirma conformidad integral WCAG 2.2 AA.
