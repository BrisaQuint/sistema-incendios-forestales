import test from "node:test";
import assert from "node:assert/strict";
import { selectCell, highlightSelection } from "../src/mapSelection.ts";
import { readFileSync } from "node:fs";
import ts from "typescript";

// Exercise the actual component effect with controlled hooks/Leaflet and local fetch.
// This verifies lifecycle and failure handling, not browser layout or accessibility.
async function mountMap({ fail = false } = {}) {
  const effects = [], states = [], listeners = new Map(), requests = [];
  let removed = 0, disconnected = 0, refIndex = 0;
  const container = { setAttribute() {} };
  const hooks = {
    useRef(value) { return { current: refIndex++ === 0 ? container : value }; },
    useState(value) { const i = states.length; states.push(value); return [value, next => { states[i] = next; }]; },
    useEffect(callback) { effects.push(callback); },
  };
  const map = { fitBounds() {}, invalidateSize() {}, remove() { removed++; } };
  const leaflet = {
    map() { return map; },
    control: { zoom() { return { addTo() {} }; } },
    geoJSON(data, options) {
      for (const feature of data.features) options.onEachFeature?.(feature, {
        on(event, callback) { listeners.set(feature.properties.weather_id, callback); },
        bindTooltip() {}, setStyle() {}, bringToFront() {},
      });
      return { addTo() { return this; }, getBounds() { return {}; } };
    },
  };
  const previous = { fetch: globalThis.fetch, document: globalThis.document, ResizeObserver: globalThis.ResizeObserver };
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (fail) throw new Error("controlled local failure");
    return { ok: true, json: async () => ({ release_id: "test", features: [] }) };
  };
  globalThis.document = { createElement: () => ({ textContent: "" }) };
  globalThis.ResizeObserver = class { observe() {} disconnect() { disconnected++; } };
  const source = readFileSync(new URL("../src/WeatherLocationMap.tsx", import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  const selected = [];
  const require = name => {
    if (name === "react") return hooks;
    if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    if (name === "leaflet") return leaflet;
    if (name.endsWith(".css")) return {};
    if (name === "./mapSelection") return { selectCell, highlightSelection };
    throw new Error(`Unexpected dependency: ${name}`);
  };
  try {
    new Function("require", "exports", output)(require, exports);
    exports.default({ coverage: { release_id: "test", features: [
      { properties: { weather_id: "interior", center_inside: true } },
      { properties: { weather_id: "exterior", center_inside: false } },
    ] }, selectedId: "interior", onSelect: id => selected.push(id) });
    const cleanup = effects[0]();
    await new Promise(resolve => setImmediate(resolve));
    effects[1]();
    listeners.get("exterior")?.();
    cleanup();
    return { states, requests, selected, removed, disconnected };
  } finally {
    Object.assign(globalThis, previous);
  }
}

test("componente: solo GET local, selección exterior y limpieza al desmontar", async () => {
  const result = await mountMap();
  assert.deepEqual(result.selected, ["exterior"]);
  assert.equal(result.requests.length, 1);
  assert.equal(result.requests[0].url, "/api/coverage/province");
  assert.equal(result.requests[0].options.method, undefined); // default GET
  assert.equal(result.requests[0].options.signal.aborted, true);
  assert.equal(result.removed, 1);
  assert.equal(result.disconnected, 1);
  assert.deepEqual(result.states, [false, false, true]);
});

test("componente: fallo de carga termina espera sin seleccionar ni analizar", async () => {
  const result = await mountMap({ fail: true });
  assert.deepEqual(result.states, [true, false, false]);
  assert.deepEqual(result.selected, []);
  assert.equal(result.removed, 0);
});

test("selección exacta sin filtrar centros exteriores", () => {
  const ids = new Set(["-30.75000_-66.25000", "exterior"]);
  const state = { id: "" };
  const choose = id => { state.id = id; };
  selectCell("-30.75000_-66.25000", ids, choose);
  assert.equal(state.id, "-30.75000_-66.25000");
  selectCell("exterior", ids, choose);
  assert.equal(state.id, "exterior");
  selectCell("coordenada aproximada", ids, choose);
  assert.equal(state.id, "exterior");
});

test("resaltado bidireccional conserva las capas y permite limpiar selección", () => {
  const layer = () => ({ style: null, front: 0, setStyle(style) { this.style = style; }, bringToFront() { this.front++; } });
  const a = layer(), b = layer();
  const layers = new Map([["a", a], ["b", b]]);
  highlightSelection(layers, "a");
  assert.equal(a.style.weight, 4);
  assert.equal(b.style.weight, 1);
  highlightSelection(layers, "b");
  assert.equal(a.style.weight, 1);
  assert.equal(b.style.weight, 4);
  assert.equal(b.front, 1);
  highlightSelection(layers, "");
  assert.equal(b.style.weight, 1);
  assert.equal(layers.size, 2);
});
