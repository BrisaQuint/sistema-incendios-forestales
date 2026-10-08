import { useEffect, useMemo, useRef, useState } from "react";
import type { components } from "./api/generated";

type Coverage = components["schemas"]["CoverageResponse"];
type CoverageFeature = components["schemas"]["CoverageFeature"];
type Analysis = components["schemas"]["AnalysisResult"];
type DataValue = components["schemas"]["DataValue"];
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

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [weatherId, setWeatherId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [activeDate, setActiveDate] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysisState, setAnalysisState] = useState<
    "idle" | "running" | "complete" | "error"
  >("idle");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [loadingCoverage, setLoadingCoverage] = useState(true);
  const requestSequence = useRef(0);

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
    setWeatherId(nextWeatherId);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function updatePeriodStart(value: string) {
    setPeriodStart(value);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function updatePeriodEnd(value: string) {
    setPeriodEnd(value);
    setAnalysisError(null);
    setAnalysisState("idle");
  }

  function updateActiveDate(value: string) {
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

      for (let attempt = 0; attempt < 60; attempt += 1) {
        const resultResponse = await fetch(
          `/api/analyses/${encodeURIComponent(accepted.analysis_id)}`,
        );
        const result = await readJson<Analysis>(resultResponse);
        if (result.state === "completed" || result.state === "partial") {
          if (requestSequence.current === requestId) {
            setAnalysis(result);
            setAnalysisState("complete");
          }
          return;
        }
        if (result.state === "failed") {
          throw new Error(
            result.error_message ?? "El análisis no pudo completarse.",
          );
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error(
        "El análisis sigue en curso; vuelva a consultarlo en un momento.",
      );
    } catch (error) {
      if (requestSequence.current === requestId) {
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
                {analysis.state === "completed"
                  ? "Completado · determinístico"
                  : "Parcial · resultado determinístico"}
              </span>
            </div>

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
                  <p className="metric-label">Síntesis</p>
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
                    Fuentes y limitaciones
                    <span className="summary-meta">Método y procedencia</span>
                  </summary>
                  <div className="detail-content">
                    <ul className="source-list">
                      {result.provenance.source_references.map((source) => (
                        <li key={source.source_id}>
                          <strong>{source.name}</strong> — {source.reference}
                        </li>
                      ))}
                    </ul>
                    <p>
                      Período de análisis:{" "}
                      {result.provenance.date_coverage.analysis.start} a{" "}
                      {result.provenance.date_coverage.analysis.end}. El período
                      2020 se utiliza para el spin-up del FWI. Release{" "}
                      {result.provenance.release_id}; manifest SHA-256{" "}
                      {result.provenance.manifest_sha256}.
                    </p>
                    <p>
                      La diferencia con la referencia es descriptiva, no una
                      predicción, relación causal ni evaluación de desempeño
                      predictivo. El FWI describe peligro meteorológico y no
                      constituye probabilidad de incendio ni alerta oficial.
                    </p>
                    <ul className="quality-list">
                      {Object.entries(result.provenance.quality_checks).map(
                        ([name, check]) => (
                          <li key={name}>
                            {name}: {String(check.observed)} · {check.status}
                          </li>
                        ),
                      )}
                    </ul>
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
