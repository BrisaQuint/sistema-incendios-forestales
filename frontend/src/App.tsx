import { useEffect, useMemo, useRef, useState } from "react";
import type { components } from "./api/generated";

type Coverage = components["schemas"]["CoverageResponse"];
type CoverageFeature = components["schemas"]["CoverageFeature"];
type Analysis = components["schemas"]["AnalysisResult"];
type DataValue = components["schemas"]["DataValue"];
type Trace = components["schemas"]["TraceResponse"];
type TraceEvent = components["schemas"]["TraceEventView"];
type RequestError = {
  error?: {
    code?: string;
    message?: string;
  };
};

const COMPONENTS = [
  ["FFMC", "ffmc"],
  ["DMC", "dmc"],
  ["DC", "dc"],
  ["ISI", "isi"],
  ["BUI", "bui"],
] as const;

const METEOROLOGY = [
  ["Temperatura a 2 m", "temperature_2m"],
  ["Humedad relativa a 2 m", "relative_humidity_2m"],
  ["Velocidad del viento a 10 m", "wind_speed_10m"],
  ["Precipitación", "rain_24h"],
] as const;

function isCoverage(value: unknown): value is Coverage {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    value.type === "FeatureCollection" &&
    "features" in value &&
    Array.isArray(value.features) &&
    "date_coverage" in value &&
    typeof value.date_coverage === "object" &&
    value.date_coverage !== null &&
    "analysis" in value.date_coverage
  );
}

async function readJson<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json();
  if (!response.ok) {
    const error = payload as RequestError;
    throw new Error(
      error.error?.message ?? `La solicitud falló (HTTP ${response.status}).`,
    );
  }
  return payload as T;
}

function dateIsInRange(value: string, start: string, end: string): boolean {
  return Boolean(value && start && end && value >= start && value <= end);
}

function everyDateIsAvailable(
  start: string,
  end: string,
  availableDates: Set<string>,
): boolean {
  if (!start || !end || start > end) return false;
  const cursor = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  while (cursor <= last) {
    const day = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}-${String(cursor.getDate()).padStart(2, "0")}`;
    if (!availableDates.has(day)) return false;
    cursor.setDate(cursor.getDate() + 1);
  }
  return true;
}

function displayValue(data: DataValue | undefined): string {
  if (!data || data.value === null) {
    return data?.missing_reason
      ? `No disponible (${data.missing_reason})`
      : "No disponible";
  }
  return new Intl.NumberFormat("es-AR", {
    maximumFractionDigits: 2,
  }).format(data.value);
}

type QualityChecks =
  components["schemas"]["SnapshotProvenance"]["quality_checks"];
function qualityNumber(
  checks: QualityChecks,
  key: string,
): number | null {
  const check = checks[key];
  return check?.status === "passed" &&
    typeof check.observed === "number" &&
    Number.isFinite(check.observed)
    ? check.observed
    : null;
}

function formatCount(value: number | null): string {
  return value === null
    ? "No disponible"
    : new Intl.NumberFormat("es-AR", {
        maximumFractionDigits: 0,
      }).format(value);
}

const QUALITY_LABELS: Record<string, string> = {
  analysis_cell_days: "Celdas-día del período analítico",
  duplicate_weather_date_keys: "Claves de ubicación y fecha duplicadas",
  firms_detected_cell_days: "Celdas-día con detecciones FIRMS asociadas",
  firms_detection_count: "Detecciones FIRMS individuales",
  missing_values: "Valores faltantes",
  negative_fwi_components: "Componentes FWI negativos",
  non_finite_scientific_values: "Valores científicos no finitos",
  weather_daily_records: "Registros meteorológicos diarios",
  weather_location_count: "Ubicaciones meteorológicas",
};

function qualityLabel(key: string): string {
  if (QUALITY_LABELS[key]) return QUALITY_LABELS[key];

  const yearlyRecords = /^weather_daily_records_(\d{4})$/.exec(key);
  if (yearlyRecords) {
    return `Registros meteorológicos de ${yearlyRecords[1]}`;
  }

  return key.replaceAll("_", " ");
}

function sourceLabel(sourceId: string, originalName: string): string {
  const id = sourceId.toLowerCase();

  if (id.includes("ign") || id.includes("boundary")) {
    return "Instituto Geográfico Nacional (IGN)";
  }
  if (id.includes("open") || id.includes("era5") || id.includes("weather")) {
    return "Datos meteorológicos históricos — Open-Meteo / ERA5";
  }
  if (id.includes("fwi") || id.includes("cffdrs")) {
    return "Sistema canadiense de índices meteorológicos de incendios (FWI)";
  }
  if (id.includes("firms") || id.includes("viirs")) {
    return "Detecciones térmicas históricas — NASA FIRMS VIIRS S-NPP";
  }

  return originalName;
}

function dataStatus(data: DataValue | undefined): string {
  return !data || data.value === null
    ? `Dato no disponible${data?.missing_reason ? `: ${data.missing_reason}` : ""}`
    : "Disponible";
}

function featureLabel(feature: CoverageFeature): string {
  const { weather_id: weatherId, center } = feature.properties;
  return `${weatherId} · centro ${center.latitude.toFixed(3)}, ${center.longitude.toFixed(3)}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Ocurrió un error inesperado al consultar FireWatch.";
}

function isTerminalState(state: Analysis["state"]): boolean {
  return state === "completed" || state === "partial" || state === "failed";
}

function mergeTrace(
  current: Trace | null,
  incoming: Trace,
  analysisId: string,
): Trace {
  const events = new Map<string, TraceEvent>();
  for (const event of current?.events ?? []) {
    if (event.analysis_id === analysisId) {
      events.set(`${event.analysis_id}:${event.sequence}`, event);
    }
  }
  for (const event of incoming.events) {
    if (event.analysis_id === analysisId) {
      events.set(`${event.analysis_id}:${event.sequence}`, event);
    }
  }
  return {
    ...incoming,
    events: [...events.values()].sort(
      (left, right) =>
        left.analysis_id.localeCompare(right.analysis_id) ||
        left.sequence - right.sequence,
    ),
  };
}

function runStateLabel(state: Analysis["state"]): string {
  return {
    queued: "En cola",
    running: "En curso",
    completed: "Completado",
    partial: "Parcial",
    failed: "Error",
  }[state];
}

function traceAvailabilityLabel(status: Trace["trace_status"]): string {
  return {
    not_yet_recorded: "Traza aún no registrada",
    available: "Traza disponible",
    incomplete: "Traza incompleta",
    unavailable: "Traza no disponible",
  }[status];
}


const AGENT_ROLES = [
  ["contextualizer", "Contextualizador"],
  ["validator", "Validador"],
  ["explainer", "Explicador"],
] as const;

function agentSummary(
  events: TraceEvent[],
  role: string,
  runState: Trace["run_state"],
): { state: string; result: string } {
  const agentEvents = events.filter(
    (event) => event.agent_role === role,
  );

  const latest = [...agentEvents].sort(
    (a, b) => b.sequence - a.sequence,
  )[0];

  if (!latest) {
    return {
      state:
        runState === "completed" ||
        runState === "partial" ||
        runState === "failed"
          ? "No ejecutado / sin registro"
          : "Pendiente",
      result: "No hay intervención registrada para este agente.",
    };
  }

  const failed = agentEvents.find(
    (event) =>
      event.event_type === "intervention_failed" ||
      Boolean(event.error_code),
  );

  if (failed) {
    return {
      state: "Fallido",
      result: failed.error_code
        ? `Error ${failed.error_code}`
        : "La intervención falló.",
    };
  }

  const completed = agentEvents.find(
    (event) => event.event_type === "intervention_completed",
  );

  if (completed) {
    const approved =
      role === "validator" &&
      events.some(
        (event) =>
          event.event_type === "review_approved" &&
          event.intervention_id === completed.intervention_id,
      );

    return {
      state: approved ? "Aprobado" : "Completado",
      result: approved
        ? "Revisión aprobada"
        : completed.result_summary ??
          "Intervención completada.",
    };
  }

  return {
    state: "En curso",
    result: latest.task ?? "Intervención iniciada.",
  };
}


function TraceInspection({
  trace,
  traceError,
  connection,
}: {
  trace: Trace | null;
  traceError: string | null;
  connection: "idle" | "connecting" | "connected" | "reconnecting";
}) {
  return (
    <section className="trace-inspection" aria-labelledby="trace-title">
      <details>
        <summary>
          <span id="trace-title">Traza real del análisis</span>
          <span className="summary-meta">
            {trace
              ? `${traceAvailabilityLabel(trace.trace_status)} · ${runStateLabel(trace.run_state)}`
              : "Cargando eventos persistidos"}
          </span>
        </summary>
        <div className="detail-content">
          <p className="trace-status" role="status" aria-live="polite">
            {trace
              ? `${traceAvailabilityLabel(trace.trace_status)}. Estado del run: ${runStateLabel(trace.run_state)}.`
              : traceError
                ? `Traza no disponible: ${traceError}`
                : "Consultando únicamente eventos confirmados en el almacenamiento durable."}
            {connection === "connecting" && " Conectando al stream."}
            {connection === "reconnecting" &&
              ` Conexión interrumpida; reconectando desde la secuencia ${trace?.latest_sequence ?? 0}.`}
            {connection === "connected" && " Stream conectado."}
            {traceError && ` Error al actualizar la traza: ${traceError}`}
          </p>
          {trace && trace.events.length === 0 ? (
            <p>
              {trace.trace_status === "unavailable"
                ? "La traza no está disponible para este análisis."
                : "La traza aún no está registrada."}
           </p>
          ) : trace?.events.length ? (
            <>
              <h3>Intervenciones multiagente</h3>

          <div
            className="table-scroll"
            role="region"
            aria-label="Resumen de intervenciones multiagente"
            tabIndex={0}
          >
            <table className="data-list trace-list">
              <thead>
                <tr>
                  <th scope="col">Agente</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {AGENT_ROLES.map(([role, label]) => {
                  const summary = agentSummary(
                    trace.events,
                    role,
                    trace.run_state,
                  );

                  return (
                    <tr key={role}>
                      <td>{label}</td>
                      <td>{summary.state}</td>
                      <td>{summary.result}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
          ) : (
            <p>
              La traza todavía no está disponible para este análisis. No se
              sustituye por actividad simulada.
            </p>
          )}
        </div>
      </details>
    </section>
  );
}

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [weatherId, setWeatherId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [activeDate, setActiveDate] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [restoredAnalysis, setRestoredAnalysis] = useState(false);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceConnection, setTraceConnection] = useState<
    "idle" | "connecting" | "connected" | "reconnecting"
  >("idle");
  const [analysisState, setAnalysisState] = useState<
    "idle" | "running" | "complete" | "error"
  >("idle");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [loadingCoverage, setLoadingCoverage] = useState(true);
  const requestSequence = useRef(0);
  const eventSource = useRef<EventSource | null>(null);
  const cancelTraceStream = useRef<(() => void) | null>(null);

  useEffect(
    () => () => {
      cancelTraceStream.current?.();
      eventSource.current?.close();
    },
    [],
  );
  useEffect(() => {
    const analysisId = new URLSearchParams(window.location.search).get(
      "analysis_id",
    );

    if (!analysisId) return;

    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(analysisId)) {
      setAnalysisError("El identificador del análisis no es válido.");
      setAnalysisState("error");
      return;
    }

    const controller = new AbortController();

    async function loadSavedAnalysis() {
      setAnalysisState("running");
      setAnalysisError(null);

      try {
        const id = encodeURIComponent(analysisId!);

        const [savedAnalysis, savedTrace] = await Promise.all([
          fetch(`/api/analyses/${id}`, { signal: controller.signal }).then(
            (response) => readJson<Analysis>(response),
          ),
          fetch(`/api/analyses/${id}/trace`, {
            signal: controller.signal,
          }).then((response) => readJson<Trace>(response)),
        ]);

        if (controller.signal.aborted) return;

        setAnalysis(savedAnalysis);
        setRestoredAnalysis(true);
        setTrace(savedTrace);
        setTraceConnection("idle");
        setAnalysisState(
          isTerminalState(savedAnalysis.state) ? "complete" : "running",
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        setAnalysisError(errorMessage(error));
        setAnalysisState("error");
      }
    }

    void loadSavedAnalysis();

    return () => controller.abort();
  }, []);


  function closeTraceStream() {
    requestSequence.current += 1;
    cancelTraceStream.current?.();
    eventSource.current?.close();
    eventSource.current = null;
    setTraceConnection("idle");
  }

  async function loadCoverage() {
    setLoadingCoverage(true);
    setCoverageError(null);
    try {
      const response = await fetch("/api/coverage");
      const payload: unknown = await readJson(response);
      if (!isCoverage(payload)) {
        throw new Error("La cobertura recibida no cumple el contrato esperado.");
      }
      setCoverage(payload);
    } catch (error) {
      setCoverageError(errorMessage(error));
    } finally {
      setLoadingCoverage(false);
    }
  }

  useEffect(() => {
    void loadCoverage();
  }, []);

  const selectedFeature = useMemo(
    () =>
      coverage?.features.find(
        (feature) => feature.properties.weather_id === weatherId,
      ) ?? null,
    [coverage, weatherId],
  );
  const availableDates = useMemo(
    () => new Set(selectedFeature?.properties.available_dates ?? []),
    [selectedFeature],
  );
  const dateRange = coverage?.date_coverage.analysis;
  const periodIsValid = everyDateIsAvailable(
    periodStart,
    periodEnd,
    availableDates,
  );
  const activeDateIsValid =
    periodIsValid && dateIsInRange(activeDate, periodStart, periodEnd);
  const canRun =
    Boolean(selectedFeature) &&
    activeDateIsValid &&
    analysisState !== "running" &&
    !loadingCoverage;

  function chooseLocation(nextWeatherId: string) {
    closeTraceStream();
    setWeatherId(nextWeatherId);
    setAnalysis(null);
    setTrace(null);
    setTraceError(null);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function updatePeriodStart(value: string) {
    closeTraceStream();
    setAnalysis(null);
    setTrace(null);
    setPeriodStart(value);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function updatePeriodEnd(value: string) {
    closeTraceStream();
    setAnalysis(null);
    setTrace(null);
    setPeriodEnd(value);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function updateActiveDate(value: string) {
    closeTraceStream();
    setAnalysis(null);
    setTrace(null);
    setActiveDate(value);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function navigateDate(offset: -1 | 1) {
    if (!activeDateIsValid) return;
    const cursor = new Date(`${activeDate}T12:00:00`);
    cursor.setDate(cursor.getDate() + offset);
    const nextDate = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}-${String(cursor.getDate()).padStart(2, "0")}`;
    if (dateIsInRange(nextDate, periodStart, periodEnd)) {
      updateActiveDate(nextDate);
    }
  }

  async function executeAnalysis(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canRun || !selectedFeature) return;

    const selectedWeatherId = selectedFeature.properties.weather_id;
    const selectedDay = activeDate;
    const requestId = ++requestSequence.current;
    setAnalysis(null);
    setTrace(null);
    setTraceError(null);
    setAnalysisError(null);
    setAnalysisState("running");

    try {
      const acceptedResponse = await fetch("/api/analyses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          weather_id: selectedWeatherId,
          date: selectedDay,
        }),
      });
      const accepted = await readJson<{
        analysis_id: string;
        state: "queued";
      }>(acceptedResponse);
      const traceUrl = `/api/analyses/${encodeURIComponent(accepted.analysis_id)}/trace`;
      const initialTrace = await readJson<Trace>(await fetch(traceUrl));
      if (requestSequence.current !== requestId) return;
      setTrace(initialTrace);
      const currentAnalysis = await readJson<Analysis>(
        await fetch(`/api/analyses/${encodeURIComponent(accepted.analysis_id)}`),
      );
      setAnalysis(currentAnalysis);
      if (isTerminalState(initialTrace.run_state)) {
        setAnalysis(currentAnalysis);
        setAnalysisState("complete");
        return;
      }

      const source = new EventSource(
        `/api/analyses/${encodeURIComponent(accepted.analysis_id)}/trace/events`,
      );
      eventSource.current = source;
      setTraceConnection("connecting");
      await new Promise<void>((resolve, reject) => {
        let finished = false;
        const finish = () => {
          if (finished) return;
          finished = true;
          source.close();
          if (eventSource.current === source) eventSource.current = null;
          if (cancelTraceStream.current === finish) {
            cancelTraceStream.current = null;
          }
          setTraceConnection("idle");
          resolve();
        };
        cancelTraceStream.current = finish;
        const refresh = async (event: MessageEvent<string>) => {
          try {
            const persisted = JSON.parse(event.data) as {
              analysis_id: string;
              sequence: number;
              event_type: string;
            };
            if (persisted.analysis_id !== accepted.analysis_id) return;
            const updatedTrace = await readJson<Trace>(await fetch(traceUrl));
            if (requestSequence.current !== requestId) {
              finish();
              return;
            }
            setTrace((current) =>
              mergeTrace(current, updatedTrace, persisted.analysis_id),
            );
            setTraceConnection("connected");
            if (isTerminalState(updatedTrace.run_state)) {
              const result = await readJson<Analysis>(
                await fetch(
                  `/api/analyses/${encodeURIComponent(accepted.analysis_id)}`,
                ),
              );
              if (requestSequence.current === requestId) {
                setAnalysis(result);
                setAnalysisState("complete");
              }
              finish();
            }
          } catch (error) {
            setTraceError(errorMessage(error));
            finish();
            reject(error);
          }
        };
        const eventTypes = [
          "run_queued",
          "run_started",
          "analysis_core_result_persisted",
          "tool_failed",
          "intervention_started",
          "intervention_completed",
          "intervention_failed",
          "review_approved",
          "review_revision_requested",
          "run_interrupted",
          "run_completed",
          "run_partial",
          "run_failed",
        ];
        for (const eventType of eventTypes) {
          source.addEventListener(eventType, (event) => {
            void refresh(event as MessageEvent<string>);
          });
        }
        source.onopen = () => setTraceConnection("connected");
        source.onerror = () => setTraceConnection("reconnecting");
      });
    } catch (error) {
      if (requestSequence.current === requestId) {
        closeTraceStream();
        setAnalysisError(errorMessage(error));
        setAnalysisState("error");
      }
    }
  }

  const result = analysis?.result;
  const resultFeature =
    analysis === null
      ? null
      : coverage?.features.find(
          (feature) =>
            feature.properties.weather_id === analysis.weather_id,
        ) ?? null;
  const difference = result?.difference_from_reference.value;
  const summary =
    difference === null || difference === undefined
      ? "No es posible comparar este valor con una referencia histórica disponible para la misma ubicación y mes."
      : difference > 0
        ? "El FWI observado está por encima de la mediana histórica local-mensual. Esta diferencia describe condiciones meteorológicas; no predice ni confirma un incendio."
        : difference < 0
          ? "El FWI observado está por debajo de la mediana histórica local-mensual. Esta diferencia describe condiciones meteorológicas; no predice ni confirma un incendio."
          : "El FWI observado coincide con la mediana histórica local-mensual. Esta comparación describe condiciones meteorológicas; no predice ni confirma un incendio.";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="/" aria-label="FireWatch, inicio">
            <span>Fire</span>Watch
          </a>
          <p className="scope-label">Análisis histórico · La Rioja, Argentina</p>
        </div>
      </header>

      <main>
        <section className="intro" aria-labelledby="page-title">
          <p className="eyebrow">Análisis ambiental</p>
          <h1 id="page-title">Peligro meteorológico de incendio</h1>
          <p>
            Explore las condiciones meteorológicas históricas y su contexto.
            FireWatch no predice la ocurrencia de incendios.
          </p>
        </section>

        <p className="concept-note">
          Los resultados se obtienen del snapshot científico validado. Cada
          fecha se analiza por separado; no se calcula un FWI agregado para el
          período.
        </p>

        <form className="context" aria-label="Contexto del análisis" onSubmit={executeAnalysis}>
          <div className="field">
            <label htmlFor="location">Ubicación o sector de La Rioja</label>
            <select
              id="location"
              name="weather_id"
              value={weatherId}
              onChange={(event) => chooseLocation(event.target.value)}
              disabled={loadingCoverage || !coverage}
              required
            >
              <option value="">Seleccionar ubicación o sector</option>
              {coverage?.features.map((feature) => (
                <option
                  key={feature.properties.weather_id}
                  value={feature.properties.weather_id}
                >
                  {featureLabel(feature)}
                </option>
              ))}
            </select>
            <small>
              El identificador y centro corresponden a una ubicación incluida
              en la cobertura disponible.
            </small>
          </div>

          <div className="field">
            <label htmlFor="period-start">Inicio del período disponible</label>
            <input
              id="period-start"
              type="date"
              value={periodStart}
              min={dateRange?.start}
              max={dateRange?.end}
              onChange={(event) => updatePeriodStart(event.target.value)}
              disabled={!selectedFeature}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="period-end">Fin del período disponible</label>
            <input
              id="period-end"
              type="date"
              value={periodEnd}
              min={dateRange?.start}
              max={dateRange?.end}
              onChange={(event) => updatePeriodEnd(event.target.value)}
              disabled={!selectedFeature}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="analysis-date">Día que se analizará</label>
            <input
              id="analysis-date"
              type="date"
              value={activeDate}
              min={dateRange?.start}
              max={dateRange?.end}
              onChange={(event) => updateActiveDate(event.target.value)}
              disabled={!selectedFeature}
              required
              aria-describedby="date-help"
            />
            <small id="date-help">
              Cada ejecución consulta un solo día del período.
            </small>
          </div>

          <button className="button" type="submit" disabled={!canRun}>
            {analysisState === "running" ? "Analizando…" : "Ejecutar este día"}
          </button>
        </form>

        <p className="coverage-help" role="status" aria-live="polite">
          {loadingCoverage
            ? "Cargando cobertura y fechas disponibles…"
            : coverageError
              ? `No se pudo cargar la cobertura: ${coverageError}`
              : !selectedFeature
                ? "Seleccione una ubicación incluida en la cobertura para definir el período."
                : periodStart && periodEnd && periodStart > periodEnd
                  ? "El inicio del período debe ser anterior o igual al fin."
                  : periodStart && periodEnd && !periodIsValid
                    ? "El período contiene fechas fuera de la cobertura de esta ubicación. La selección se conserva; elija fechas disponibles."
                    : activeDate && !activeDateIsValid
                      ? "El día elegido debe estar dentro del período y de las fechas disponibles para esta ubicación. La selección se conserva."
                      : "Solo se pueden ejecutar fechas disponibles para la ubicación elegida."}
          {coverageError && (
            <button className="text-button" type="button" onClick={() => void loadCoverage()}>
              Reintentar
            </button>
          )}
        </p>

        {selectedFeature && (
          <section className="selected-context" aria-label="Contexto seleccionado">
            <span>
              <strong>Ubicación:</strong> {featureLabel(selectedFeature)}
            </span>
            <span>
              <strong>Período:</strong>{" "}
              {periodStart && periodEnd
                ? `${periodStart} a ${periodEnd}`
                : "sin definir"}
            </span>
            <span>
              <strong>Día:</strong> {activeDate || "sin definir"}
            </span>
            <div className="day-navigation" aria-label="Navegación diaria">
              <button
                type="button"
                onClick={() => navigateDate(-1)}
                disabled={
                  !activeDateIsValid || activeDate <= periodStart
                }
              >
                Día anterior
              </button>
              <button
                type="button"
                onClick={() => navigateDate(1)}
                disabled={!activeDateIsValid || activeDate >= periodEnd}
              >
                Día siguiente
              </button>
            </div>
          </section>
        )}

        {analysisState === "running" && (
          <p className="state-message" role="status" aria-live="polite">
            Consultando resultado determinístico para {weatherId} · {activeDate}.
            El contexto seleccionado se mantiene visible.
          </p>
        )}
        {analysisError && (
          <p className="state-message error-message" role="alert">
            No se pudo completar la consulta para {weatherId} · {activeDate}:{" "}
            {analysisError} Se conserva la ubicación y fecha seleccionadas;
            puede corregir el contexto e intentar de nuevo.
          </p>
        )}
        {coverageError && (
          <p className="state-message error-message" role="alert">
            No hay resultados de cobertura disponibles hasta que el servicio
            responda correctamente.
          </p>
        )}

        {analysis && (
          <TraceInspection
            trace={trace}
            traceError={traceError}
            connection={traceConnection}
          />
        )}

        {analysis && restoredAnalysis && (
          <p className="subline" role="status">
            Análisis histórico recuperado · Ubicación: {analysis.weather_id}
            {" · "}Fecha: {analysis.date}.
            Los selectores superiores no representan necesariamente
            este resultado guardado.
          </p>
        )}

        {analysis && !result && isTerminalState(analysis.state) && (
          <section
            className="state-message error-message"
            aria-labelledby="analysis-unavailable-title"
          >
            <h2 id="analysis-unavailable-title">
              {analysis.state === "partial" ? "Análisis parcial" : "Análisis con error"}
            </h2>
            <p>
              {analysis.error_message ??
                "No hay un resultado determinístico disponible para este run."}
            </p>
            {analysis.error_code && <p>Código: {analysis.error_code}</p>}
            {(analysis.affected_outputs ?? []).length > 0 && (
              <p>
                Tarea/salida afectada: {analysis.affected_outputs?.join(", ")}.
              </p>
            )}
          </section>
        )}

        {analysis && result && (
          <>
            <div className="selected-context result-context" aria-label="Contexto del resultado">
              <span>
                <strong>Ubicación del resultado:</strong>{" "}
                {analysis.weather_id}
                {resultFeature
                  ? ` · centro ${resultFeature.properties.center.latitude.toFixed(3)}, ${resultFeature.properties.center.longitude.toFixed(3)}`
                  : ""}
              </span>
              <span>
                <strong>Fecha:</strong> {analysis.date}
              </span>
              <span className="status">
                <span className="status-mark" aria-hidden="true" />
                {runStateLabel(analysis.state)} · resultado determinístico
              </span>
            </div>
            {analysis.state === "partial" && (
              <p className="state-message trace-partial" role="status">
                Análisis parcial: {analysis.error_message ?? "una rama del análisis no está disponible."}
                {(analysis.affected_outputs ?? []).length > 0 && (
                  <> Salida afectada: {analysis.affected_outputs?.join(", ")}.</>
                )}
              </p>
            )}
            {analysis.state === "failed" && (
              <p className="state-message error-message" role="alert">
                Análisis con error: {analysis.error_message ?? "no hay resultado disponible."}
              </p>
            )}

            <section className="result" aria-labelledby="result-title">
              <div className="result-head">
                <div>
                  <h2 id="result-title">Resumen del análisis</h2>
                  <p className="subline">
                    El valor se interpreta junto con su referencia para la
                    misma ubicación y mes.
                  </p>
                </div>
                <span className="badge">
                  Peligro meteorológico · no es probabilidad
                </span>
              </div>

              <div className="primary-grid">
                <div className="metric">
                  <p className="metric-label">FWI observado</p>
                  <div className="metric-row">
                    <span className="metric-number">{displayValue(result.fwi)}</span>
                    <span className="metric-unit">{result.fwi.unit ?? "FWI"}</span>
                  </div>
                  <p className="metric-caption">{dataStatus(result.fwi)}</p>
                </div>

                <div className="compare" aria-label="Comparación con la referencia histórica">
                  <div className="compare-top">
                    <strong>Referencia histórica local-mensual</strong>
                    <span className="difference">
                      {result.difference_from_reference.value === null
                        ? "No disponible"
                        : `${result.difference_from_reference.value > 0 ? "+" : ""}${displayValue(result.difference_from_reference)}`}
                    </span>
                  </div>
                  <div className="compare-values">
                    <div className="compare-value">
                      <small>Mediana · mes {result.reference_month}</small>
                      <strong>
                        {displayValue(result.historical_reference_fwi)}
                      </strong>
                      <small>{dataStatus(result.historical_reference_fwi)}</small>
                    </div>
                    <div className="compare-value observed">
                      <small>FWI observado</small>
                      <strong>{displayValue(result.fwi)}</strong>
                      <small>{dataStatus(result.fwi)}</small>
                    </div>
                  </div>
                  <p className="metric-caption">
                    Diferencia descriptiva respecto de la mediana histórica de
                    esta ubicación y mes.
                  </p>
                </div>

                <div className="summary">
                  <p className="metric-label">Comparación determinística</p>
                  <p>{summary}</p>
                </div>
              </div>

              <div className="section">
                <div className="section-title">
                  <h3>Componentes FWI</h3>
                  <span>Resultados determinísticos del día seleccionado</span>
                </div>
                <div className="component-list" aria-label="Componentes FWI">
                  {COMPONENTS.map(([label, key]) => (
                    <span className="component" key={key}>
                      <b>{label}</b>
                      <span>{displayValue(result.components[key])}</span>
                    </span>
                  ))}
                  <span className="component">
                    <b>FWI</b>
                    <span>{displayValue(result.fwi)}</span>
                  </span>
                </div>
              </div>

              <div className="details-group">
                {analysis.explanation && (
                  <section className="section interpretation" aria-labelledby="interpretation-title">
                    <div className="section-title">
                      <h3 id="interpretation-title">Interpretación validada</h3>
                      <span>Separada de observaciones y cálculos</span>
                    </div>
                    <p>{analysis.explanation}</p>
                    {analysis.explanation_evidence_refs &&
                      analysis.explanation_evidence_refs.length > 0 && (
                        <ul className="source-list">
                          {analysis.explanation_evidence_refs.map((reference) => (
                            <li key={reference}>
                              <code>{reference}</code>
                            </li>
                          ))}
                        </ul>
                      )}
                  </section>
                )}

                <details>
                  <summary>
                    Variables meteorológicas
                    <span className="summary-meta">Detalle del contexto</span>
                  </summary>
                  <div className="detail-content">
                    <div className="table-scroll" role="region" aria-label="Variables meteorológicas" tabIndex={0}>
                      <table className="data-list">
                        <thead>
                          <tr>
                            <th scope="col">Variable</th>
                            <th scope="col">Valor y unidad</th>
                            <th scope="col">Estado del dato</th>
                          </tr>
                        </thead>
                        <tbody>
                          {METEOROLOGY.map(([label, key]) => {
                            const value = result.meteorology[key];
                            return (
                              <tr key={key}>
                                <td>{label}</td>
                                <td>
                                  {displayValue(value)} {value.unit ?? ""}
                                </td>
                                <td>{dataStatus(value)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="component-detail">
                      <h3>Detalle de componentes FWI</h3>
                      <dl>
                        {COMPONENTS.map(([label, key]) => (
                          <div key={key}>
                            <dt>{label}</dt>
                            <dd>
                              {displayValue(result.components[key])}{" "}
                              {result.components[key].unit ?? ""}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  </div>
                </details>

                <details>
                  <summary>
                    Evidencia FIRMS
                    <span className="summary-meta">Detecciones térmicas históricas</span>
                  </summary>
                  <div className="detail-content">
                    <div className="firms-note">
                      <strong>
                        {result.firms_count.value === 0
                          ? "No hay detecciones FIRMS asociadas a este contexto"
                          : "Detecciones FIRMS asociadas"}
                      </strong>
                      {displayValue(result.firms_count)}{" "}
                      {result.firms_count.unit ?? ""}. FIRMS type=0 significa
                      presumed vegetation fire. Una detección térmica no
                      confirma por sí sola un incendio individual; la ausencia
                      de detecciones asociadas no demuestra ausencia de
                      incendio.
                    </div>
                    <p className="subline">
                      La asociación con el FWI de las 12:00 local del mismo día
                      es histórica y descriptiva, no predictiva. Una detección
                      anterior a las 12:00 puede quedar asociada a condiciones
                      meteorológicas posteriores dentro de ese día.
                    </p>
                  </div>
                </details>


                <details>
                  <summary>
                    Fuentes, metodología y calidad
                    <span className="summary-meta">
                      Procedencia y límites del análisis
                    </span>
                  </summary>

                  <div className="detail-content provenance-section">
                    <h3>Datos utilizados</h3>

                    <dl className="provenance-summary">
                      <div>
                        <dt>Ubicaciones meteorológicas</dt>
                        <dd>
                          {formatCount(
                            qualityNumber(
                              result.provenance.quality_checks,
                              "weather_location_count",
                            ),
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Período analítico</dt>
                        <dd>
                          {result.provenance.date_coverage.analysis.start} a{" "}
                          {result.provenance.date_coverage.analysis.end}
                        </dd>
                      </div>
                      <div>
                        <dt>Registros diarios 2020–2025</dt>
                        <dd>
                          {formatCount(
                            qualityNumber(
                              result.provenance.quality_checks,
                              "weather_daily_records",
                            ),
                          )}
                        </dd>
                      </div>
                    </dl>

                    <h3>Fuentes y metodología</h3>
                    <ul className="source-list">
                      {result.provenance.source_references.map((source) => (
                        <li key={source.source_id}>
                          <strong>{sourceLabel(source.source_id, source.name)}</strong>
                        </li>
                      ))}
                    </ul>

                    <p>
                      El índice FWI clásico se calcula a partir de temperatura,
                      humedad relativa, viento y precipitación. Se utiliza
                      información meteorológica histórica, y el período
                      {` ${result.provenance.date_coverage.spin_up.start} a
                      ${result.provenance.date_coverage.spin_up.end} `}
                      permite inicializar la evolución de sus componentes.
                    </p>

                    <p>
                      La cobertura utiliza una cuadrícula de planificación de 0,25°
                      para las ubicaciones meteorológicas del área de estudio.
                      Esto no significa que todo el territorio tenga exactamente
                      esa resolución espacial de observación.
                    </p>

                    <h3>Limitaciones</h3>
                    <p>
                      El FWI describe peligro meteorológico histórico. No expresa
                      probabilidad de incendio, no predice eventos y no constituye
                      una alerta oficial. La asociación con detecciones FIRMS es
                      descriptiva y no demuestra causalidad.
                    </p>

                    <details className="provenance-subdetails">
                      <summary>Calidad y disponibilidad de datos</summary>
                      <div className="detail-content">
                        <p>
                          Controles reportados para el release{" "}
                          <strong>{result.provenance.release_id}</strong>.
                          No constituyen garantías para otras versiones.
                        </p>

                        <dl className="provenance-summary">
                          <div>
                            <dt>Celdas-día analizadas (2021–2025)</dt>
                            <dd>
                              {formatCount(
                                qualityNumber(
                                  result.provenance.quality_checks,
                                  "analysis_cell_days",
                                ),
                              )}
                            </dd>
                          </div>
                          <div>
                            <dt>Celdas-día con detecciones FIRMS</dt>
                            <dd>
                              {formatCount(
                                qualityNumber(
                                  result.provenance.quality_checks,
                                  "firms_detected_cell_days",
                                ),
                              )}
                            </dd>
                          </div>
                          <div>
                            <dt>Celdas-día sin detecciones asociadas</dt>
                            <dd>
                              {(() => {
                                const total = qualityNumber(
                                  result.provenance.quality_checks,
                                  "analysis_cell_days",
                                );
                                const detected = qualityNumber(
                                  result.provenance.quality_checks,
                                  "firms_detected_cell_days",
                                );
                                return formatCount(
                                  total !== null &&
                                    detected !== null &&
                                    detected <= total
                                    ? total - detected
                                    : null,
                                );
                              })()}
                            </dd>
                          </div>
                          <div>
                            <dt>Detecciones FIRMS individuales</dt>
                            <dd>
                              {formatCount(
                                qualityNumber(
                                  result.provenance.quality_checks,
                                  "firms_detection_count",
                                ),
                              )}
                            </dd>
                          </div>
                        </dl>

                        <p className="subline">
                          Una celda-día sin detecciones FIRMS asociadas no demuestra
                          que no haya ocurrido un incendio.
                        </p>
                    <details className="provenance-subdetails">
                      <summary>Ver controles detallados</summary>
                      <div className="detail-content">
                        <ul className="quality-list">
                          {Object.entries(result.provenance.quality_checks).map(
                            ([name, check]) => (
                              <li key={name}>
                                <strong>{qualityLabel(name)}</strong>:{" "}
                                {typeof check.observed === "number"
                                  ? new Intl.NumberFormat("es-AR").format(check.observed)
                                  : String(check.observed)}
                                {" · "}
                                {check.status === "passed"
                                  ? "Control aprobado"
                                  : "Estado no disponible"}
                              </li>
                            ),
                          )}
                        </ul>
                      </div>
                    </details>

                      </div>
                    </details>

                    <details className="provenance-subdetails">
                      <summary>Referencias y procedencia técnica</summary>
                      <div className="detail-content">
                        <ul className="source-list">
                          {result.provenance.source_references.map((source) => (
                            <li key={source.source_id}>
                              <strong>{source.name}</strong> — {source.reference}
                            </li>
                          ))}
                        </ul>

                        <p>
                          Release: {result.provenance.release_id}
                          <br />
                          Versión del bundle: {result.provenance.bundle_version}
                          <br />
                          Versión del esquema: {result.provenance.schema_version}
                        </p>

                        <p className="technical-digest">
                          SHA-256 del manifiesto:{" "}
                          <code>{result.provenance.manifest_sha256}</code>
                        </p>
                      </div>
                    </details>
                  </div>
                </details>


              </div>
            </section>
          </>
        )}
      </main>

      <footer className="footer-note">
        <strong>Alcance:</strong> FireWatch analiza peligro meteorológico
        histórico. No predice incendios ni constituye una alerta oficial.
      </footer>
    </div>
  );
}
