import { useEffect, useRef, useState } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { components } from "./api/generated";
import { highlightSelection, selectCell } from "./mapSelection";

type Coverage = components["schemas"]["CoverageResponse"];
type Province = components["schemas"]["ProvinceBoundaryResponse"];

export default function WeatherLocationMap({ coverage, selectedId, onSelect }: {
  coverage: Coverage; selectedId: string; onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const layers = useRef(new Map<string, L.Path>());
  const select = useRef(onSelect);
  select.current = onSelect;
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let map: L.Map | undefined;
    let resize: ResizeObserver | undefined;
    const ids = new Set(coverage.features.map((feature) => feature.properties.weather_id));
    setLoading(true);
    setError(false);
    setReady(false);
    async function initialize() {
      try {
        const response = await fetch("/api/coverage/province", { signal: controller.signal });
        if (!response.ok) throw new Error("boundary unavailable");
        const province: Province = await response.json();
        if (province.release_id !== coverage.release_id || !Array.isArray(province.features)) {
          throw new Error("snapshot mismatch");
        }
        if (controller.signal.aborted || !container.current) return;
        map = L.map(container.current, { zoomControl: false, scrollWheelZoom: false,
          attributionControl: false, zoomAnimation: false, fadeAnimation: false });
        L.control.zoom({ zoomInTitle: "Acercar", zoomOutTitle: "Alejar" }).addTo(map);
        container.current.setAttribute("aria-label", "Mapa de celdas disponibles de La Rioja. Selección por teclado mediante el selector de ubicación.");
        const cells = L.geoJSON(coverage, { style: { color: "#52665e", weight: 1, fillColor: "#dce5e1", fillOpacity: .3 },
          onEachFeature(feature, layer) {
            const id = feature.properties.weather_id as string;
            layers.current.set(id, layer as L.Path);
            layer.on("click", () => selectCell(id, ids, (value) => select.current(value)));
            // Text content, never HTML from snapshot properties.
            const label = document.createElement("span");
            label.textContent = `Ubicación meteorológica: ${id}`;
            layer.bindTooltip(label);
          },
        }).addTo(map);
        L.geoJSON(province, { interactive: false, style: { color: "#182522", weight: 2, fill: false } }).addTo(map);
        map.fitBounds(cells.getBounds(), { padding: [12, 12] });
        resize = new ResizeObserver(() => map?.invalidateSize());
        resize.observe(container.current);
        setReady(true);
        setLoading(false);
      } catch {
        if (!controller.signal.aborted) {
          resize?.disconnect();
          map?.remove();
          map = undefined;
          resize = undefined;
          layers.current.clear();
          setError(true);
          setLoading(false);
        }
      }
    }
    void initialize();
    return () => {
      controller.abort();
      resize?.disconnect();
      map?.remove();
      layers.current.clear();
    };
  }, [coverage]);

  useEffect(() => {
    highlightSelection(layers.current, selectedId);
  }, [selectedId, ready]);

  return <div className="location-map-panel">
    {loading && <p role="status">Cargando mapa local…</p>}
    {error && <p role="status">No se pudo cargar el mapa. Continúe con el selector de ubicación.</p>}
    <div ref={container} className="location-map" role="region" hidden={error} />
    <p className="subline">Límite provincial IGN y {coverage.features.length} celdas del snapshot {coverage.release_id}.
      Borde azul: celda seleccionada. Las celdas que intersectan la provincia siguen disponibles aunque su centro quede fuera.</p>
  </div>;
}
