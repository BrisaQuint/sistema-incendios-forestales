# Story 3.1 — Selección de ubicaciones en mapa local

Estado: aceptada y cerrada por aprobación formal del usuario. Epic 3 se cierra tras comprobar que Story 3.1 es su única historia planificada. Epic 1 y Epic 2 permanecen cerradas; no se modifican retrospectivas.

## Decisiones y alcance

Leaflet 1.9.4 estable y tipos de desarrollo, sin otras bibliotecas de ejecución. Vectores GeoJSON locales, sin teselas, CDN, geocodificación ni servicios externos. El mapa se importa y el contorno se consulta únicamente al desplegarlo; cerrar el desplegable desmonta el mapa, cancela la petición y elimina listeners y observador de tamaño.

`/api/coverage` conserva sus contratos y las 169 celdas. El nuevo GET fijo `/api/coverage/province` entrega solamente el contorno ya validado y su `release_id`, sin aceptar rutas de archivos. El contrato auxiliar y los tipos se regeneran con las convenciones existentes. No se modifica ningún contrato científico.

La selección utiliza el mismo `chooseLocation` que el selector nativo. No tiene operaciones de análisis ni POST; conserva las validaciones previas. El borde azul identifica selección, no peligro. Las coordenadas del centro geométrico y del identificador meteorológico se explican por separado. En el snapshot, 30 centros de grilla están fuera del contorno; esas celdas no se excluyen.

## Evidencia automatizada

- Prueba de recurso provincial fijo, identidad del snapshot e independencia del proveedor y de la creación de análisis, con base temporal.
- Prueba opcional del snapshot local en modo SQLite `ro`: 169 identificadores únicos iguales a los de `weather_daily`, todas las celdas intersectan y 30 centros quedan fuera. Se omite explícitamente si no está instalado el snapshot.
- Cuatro pruebas Node: selección exacta, rechazo de identificadores ajenos, actualización/limpieza del resaltado y efectos del componente real con hooks/Leaflet simulados. Verifican GET local, fallo de carga, selección exterior, cancelación y limpieza. No sustituyen interacción real en navegador.
- Suite Python: 98 pruebas aprobadas, incluida verificación real del snapshot local (sin omisión). Compilación TypeScript/Vite correcta. `git diff --check` correcto.

## Comprobaciones manuales confirmadas

Resultados comunicados y aceptados por el usuario al aprobar el cierre, diferenciados de las pruebas automatizadas anteriores:

- El mapa carga y muestra las celdas de La Rioja.
- Seleccionar una celda actualiza el selector de ubicación.
- Cambiar la ubicación en el selector actualiza el resaltado del mapa.
- Zoom, desplazamiento, teclado y presentación responsive funcionan correctamente en los escenarios revisados.
- El mapa funciona sin conexión externa.
- Seleccionar no inicia automáticamente un análisis.
- El selector HTML permanece disponible como alternativa accesible.

## Limitaciones y verificaciones no confirmadas

- No se realizaron pruebas con lector de pantalla ni se verificaron empíricamente sus anuncios. No se declara conformidad integral WCAG 2.2 AA.
- La aprobación manual no especifica anchos o porcentajes de zoom concretos; no se atribuyen verificaciones adicionales a 320 px o zoom 200%/400%.
- La limpieza de listeners, cancelación y fallo de carga tienen evidencia automatizada con simulaciones; no se confirma un ensayo manual de ciclos repetidos con StrictMode ni de bloqueo del GET o del módulo.
- La carga diferida y ausencia de POST se sustentan además en implementación y pruebas; no se presenta como realizada una inspección manual de red no informada.
- El selector es la alternativa de selección por teclado; no se promete navegación entre polígonos con flechas.

No se ejecutaron análisis ni llamadas reales a OpenAI durante la implementación o el cierre.
