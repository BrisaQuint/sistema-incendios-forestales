---
name: FireWatch
description: Sistema visual inicial para análisis ambiental histórico, claro y trazable; propuesta de prototipo, no identidad de marca definitiva.
colors:
  canvas: '#F5F7F6'
  surface: '#FFFFFF'
  surface-subtle: '#EAF0ED'
  ink-primary: '#182522'
  ink-secondary: '#495B56'
  border: '#778A84'
  primary: '#1E6259'
  primary-hover: '#184F48'
  data-blue: '#286F85'
  focus: '#005FCC'
  caution-ink: '#775006'
  caution-surface: '#FFF5D9'
  error-ink: '#A1251B'
  error-surface: '#FDECEA'
  success-ink: '#236746'
  success-surface: '#E7F4EC'
  firms-marker: '#694B83'
  map-land: '#EEF2EF'
  map-water: '#E4EDF0'
typography:
  heading:
    fontFamily: 'system-ui, Segoe UI, sans-serif'
    fontSize: 28px
    fontWeight: '650'
    lineHeight: '1.25'
  body:
    fontFamily: 'system-ui, Segoe UI, sans-serif'
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  label:
    fontFamily: 'system-ui, Segoe UI, sans-serif'
    fontSize: 14px
    fontWeight: '550'
    lineHeight: '1.4'
  caption:
    fontFamily: 'system-ui, Segoe UI, sans-serif'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.4'
  metric:
    fontFamily: 'system-ui, Segoe UI, sans-serif'
    fontSize: 32px
    fontWeight: '650'
    lineHeight: '1.15'
rounded:
  sm: 4px
  md: 6px
  lg: 8px
  full: 9999px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 24px
  '6': 32px
  '7': 40px
  '8': 48px
components:
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.surface}'
    radius: '{rounded.md}'
  interactive-focus:
    outline: '{colors.focus}'
    outline-width: 2px
    outline-offset: 2px
  data-value:
    foreground: '{colors.ink-primary}'
    font: '{typography.metric}'
  caution-state:
    background: '{colors.caution-surface}'
    foreground: '{colors.caution-ink}'
  error-state:
    background: '{colors.error-surface}'
    foreground: '{colors.error-ink}'
  success-state:
    background: '{colors.success-surface}'
    foreground: '{colors.success-ink}'
  firms-marker:
    foreground: '{colors.firms-marker}'
    shape: diamond
---

## Brand & Style

### Dirección inicial: mesa de observación ambiental

FireWatch debe leerse como una herramienta de análisis y monitoreo: sobria, clara y técnicamente confiable, con una superficie luminosa y una jerarquía centrada en datos. La dirección combina una base neutra de baja distracción con acentos verde petróleo y azul verdoso para interacción e información. Ámbar y rojo quedan restringidos a estados semánticos, nunca como color dominante por el tema de incendios.

La propuesta prioriza escritorio para la demostración académica y conserva comportamiento adaptable. Evita metáforas de emergencia, gamificación, agentes personificados, decoración sin función y efectos que compitan con la lectura del análisis. Es un sistema visual inicial del producto, no una identidad de marca definitiva ni una copia de otra interfaz.

## Colors

| Rol | Token | Uso |
|---|---|---|
| Lienzo | `{colors.canvas}` | Fondo principal claro y neutro. |
| Superficie | `{colors.surface}` | Superficies de lectura y controles que necesiten separación del lienzo. |
| Superficie secundaria | `{colors.surface-subtle}` | Agrupación discreta de detalles, sin convertir cada dato en una tarjeta decorativa. |
| Texto principal/secundario | `{colors.ink-primary}` / `{colors.ink-secondary}` | Lectura de títulos, valores, etiquetas y explicación. |
| Acción principal | `{colors.primary}` | Acción primaria e interacción seleccionada; no codifica nivel de peligro. |
| Dato/enlace | `{colors.data-blue}` | Enlaces y series informativas cuando se requiera diferenciar una serie. |
| Precaución / error / éxito | Tokens semánticos correspondientes | Mensajes de estado con texto explícito; el color no es el único indicador. No equivalen a categorías de peligro FWI. |
| Detección FIRMS | `{colors.firms-marker}` | Diferenciar visualmente detecciones observadas; acompañar siempre con forma, etiqueta o leyenda y el texto que aclare su significado. |
| Foco | `{colors.focus}` | Indicador visible de foco de teclado. |
| Mapa | `{colors.map-land}` / `{colors.map-water}` | Base cartográfica tenue, subordinada a las capas de datos. |

### Contraste comprobado

Contraste calculado con la fórmula de luminancia relativa WCAG 2.x. Las combinaciones propuestas superan el mínimo de 4,5:1 para texto normal, salvo el borde, que se verifica como elemento gráfico no textual con el mínimo de 3:1:

| Combinación | Contraste |
|---|---:|
| Texto principal sobre blanco | 15,83:1 |
| Texto secundario sobre blanco | 7,21:1 |
| Texto blanco sobre acción principal | 7,13:1 |
| Azul de datos sobre blanco | 5,67:1 |
| Texto de precaución sobre su superficie | 6,58:1 |
| Texto de error sobre su superficie | 6,57:1 |
| Texto de éxito sobre su superficie | 5,98:1 |
| Foco sobre blanco | 5,98:1 |
| Borde sobre lienzo claro | 3,39:1 |
| Borde sobre superficie secundaria | 3,16:1 |
| Marcador FIRMS sobre blanco | 7,16:1 |

La conformidad WCAG 2.2 AA se debe verificar en los componentes y estados implementados, incluidos tamaños de texto, foco de acordeones, navegación por teclado, tablas, colores de hover/selección, mapas, gráficas, overlays y combinaciones sobre superficies distintas. Los estados no deben depender solo del color. No se debe inferir conformidad integral del producto a partir de esta comprobación inicial de tokens.

Los valores FWI no reciben categorías locales ni colores de semáforo. Si una visualización utiliza una escala secuencial para mostrar magnitud, debe etiquetar valores/unidades y leyenda, no sugerir probabilidad ni una categoría local validada. No depender solo del color para comparar series, estados o detecciones.

## Typography

Usar una sans serif de sistema para evitar dependencia de fuentes remotas y mantener una lectura familiar en el entorno académico. La jerarquía propuesta es compacta y funcional: encabezados claros, cuerpo cómodo, etiquetas legibles y cifras suficientemente destacadas para una lectura rápida sin convertir el FWI en un indicador alarmista.

Usar cifras tabulares para alinear valores en métricas y tablas. Mantener nombres y unidades junto a cifras; no reducir etiquetas metodológicas hasta hacerlas ilegibles. Evitar tipografías decorativas, condensadas o display.

## Layout & Spacing

La prioridad es escritorio, con diseño adaptable para ventanas estrechas. La superficie principal debe conservar ubicación y período durante el flujo, presentar primero resultado y referencia, y permitir consultar detalles progresivamente. UJ-1 aprueba la estructura de una sola superficie con secciones expandibles. No se definen mapa obligatorio, columnas concretas ni breakpoints; la implementación debe comprobar que tablas y trazabilidad se adaptan a anchos menores sin perder legibilidad.

Usar la escala de 4 px definida en `{spacing}` para un ritmo consistente. Reservar los espacios mayores para separar grupos funcionales; usar separaciones pequeñas solo entre datos relacionados. Evitar densidad excesiva, pero no desperdiciar ancho de escritorio que ayude a comparar contexto, valores y evidencia.

## Elevation & Depth

La jerarquía se construye mediante alineación, tipografía, espaciado y contraste tonal. Usar bordes para delimitar controles o grupos que necesiten un límite claro; sombras, si se requieren, deben ser sutiles y funcionales. No acumular tarjetas con sombra ni capas flotantes decorativas.

## Shapes

Usar radios cortos: `{rounded.sm}` para controles densos, `{rounded.md}` como valor común y `{rounded.lg}` para contenedores funcionales cuando ayude a distinguirlos. Reservar `{rounded.full}` para indicadores compactos; no convertir estados o valores en chips decorativos por defecto.

## Components

- **Acción primaria:** usar `{colors.primary}` con texto blanco; mantener estados de foco teclado claros y no depender de movimiento.
- **Controles de selección:** fondo claro, etiqueta persistente y borde de foco `{colors.focus}`; comunicar errores o cobertura no disponible mediante texto.
- **Resultado FWI:** cifras con `{typography.metric}`, texto de peligro meteorológico y contexto de ubicación/período/referencia; no usar rojo/naranja dominante ni un fondo de alarma.
- **Estados:** combinar color semántico, texto explícito y, cuando ayude, forma o icono comprensible. Precaución/éxito/error nunca se deducen solo por color.
- **Visualizaciones:** priorizar comparación, leyendas legibles, valores y unidades. Distinguir series con más de color cuando sea necesario; no inventar rangos de riesgo.
- **Mapa:** tratarlo como herramienta de selección/contexto, con base tenue, capas controladas y leyenda visible. Evitar saturación de marcadores y simbología ambigua.
- **Detecciones FIRMS:** usar el token y forma `{components.firms-marker}` como propuesta de distinción, con leyenda textual “detección térmica FIRMS”; no usar iconografía que afirme incendio confirmado.
- **Trazabilidad del MAS:** presentación funcional de agente/rol, tarea, estado y resultado/evidencia. Sin avatares caricaturescos ni protagonismo visual sobre el resultado ambiental.
- **Detalles progresivos:** los grupos de variables, explicación, fuentes, limitaciones y traza se diferencian por estructura y etiquetas, no por efectos o tarjetas decorativas.
- **Tabla meteorológica:** en implementación, mostrar valores y unidades disponibles; indicar faltantes explícitamente y nunca presentarlos como cero. En anchos estrechos, adaptar la tabla sin perder legibilidad ni relación entre encabezados y celdas.
- **Trazabilidad responsive:** conservar los campos Agente / Tarea / Estado / Resultado-Evidencia y su secuencia legible en pantallas estrechas.

## Do's and Don'ts

| Hacer | Evitar |
|---|---|
| Usar neutros claros con acentos verde petróleo/azul para una lectura técnica | Hacer del rojo/naranja el color dominante por el tema de incendios |
| Reservar ámbar y rojo para estados semánticos acompañados por texto | Usar color como único indicador de peligro, estado o error |
| Mostrar el FWI como valor contextualizado con referencia y diferencia | Presentar escalas no validadas como categorías locales de riesgo |
| Diseñar el mapa para seleccionar y contextualizar datos con leyenda | Saturar el mapa o representar detecciones FIRMS como incendios confirmados |
| Representar a agentes por función, tarea, estado y evidencia reales | Usar personajes, avatares caricaturescos o animaciones que simulen actividad |
| Usar espaciado, tipografía y alineación para jerarquizar | Añadir tarjetas, sombras, gradientes o iconos de llamas sin función |
| Mantener una superficie desktop-first que responda a tamaños menores | Convertir contexto o trazabilidad en páginas separadas o hacer responsive solo como reducción |

## Mockups UJ-1 aprobados como base

Estas láminas estáticas fijan la estructura de UX aprobada para UJ-1. La dirección visual sigue siendo provisional; los mockups no fijan arquitectura ni acreditan conformidad de accesibilidad completa:

- [Superficie principal y análisis contextualizado](./mockups/key-uj1-main.html): los valores 38, 27 y +11 son el ejemplo conceptual aportado para UX; los controles no están conectados a datos.
- [Estados del análisis](./mockups/key-uj1-states.html): reglas ilustrativas para ejecución, parcialidad, datos insuficientes y detecciones FIRMS.
