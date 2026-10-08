import { useEffect, useState } from "react";
import type { components } from "./api/generated";

type ReadinessResponse = components["schemas"]["ReadinessResponse"];

function isReadinessResponse(value: unknown): value is ReadinessResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    value.status === "ready" &&
    "snapshot_version" in value &&
    typeof value.snapshot_version === "string"
  );
}

export default function App() {
  const [runtimeStatus, setRuntimeStatus] = useState<"checking" | "ready" | "unavailable">(
    "checking",
  );

  useEffect(() => {
    fetch("/api/health/ready")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Readiness request failed with HTTP ${response.status}`);
        }
        return response.json() as Promise<unknown>;
      })
      .then((payload) => {
        setRuntimeStatus(isReadinessResponse(payload) ? "ready" : "unavailable");
      })
      .catch(() => {
        setRuntimeStatus("unavailable");
      });
  }, []);

  return (
    <main className="page-shell">
      <header className="masthead">
        <a className="wordmark" href="/" aria-label="FireWatch, inicio">
          FireWatch
        </a>
        <span className="product-label">Análisis ambiental histórico</span>
      </header>

      <section className="intro" aria-labelledby="page-title">
        <p className="eyebrow">La Rioja, Argentina</p>
        <h1 id="page-title">
          Peligro meteorológico
          <br />
          de incendios forestales
        </h1>
        <p className="lead">
          Explore el índice FWI en su contexto histórico, con fuentes y método
          visibles.
        </p>
        <p className="notice" role="status">
          {runtimeStatus === "ready"
            ? "Runtime local listo. La consulta de cobertura y resultados se habilitará en las siguientes etapas de implementación."
            : "El estado del runtime local no está disponible; no se mostrarán datos ni actividad simulados."}
        </p>
      </section>

      <footer className="page-footer">
        <p>
          FireWatch describe peligro meteorológico histórico; no predice
          incendios ni constituye una alerta oficial.
        </p>
      </footer>
    </main>
  );
}
