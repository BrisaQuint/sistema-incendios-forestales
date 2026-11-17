/** Selection has no analysis, date, network or geographic nearest-point logic. */
export function selectCell(id: string, availableIds: ReadonlySet<string>, choose: (id: string) => void) {
  if (availableIds.has(id)) choose(id);
}

export type CellLayer = {
  setStyle: (style: { color: string; weight: number; fillOpacity: number }) => unknown;
  bringToFront: () => unknown;
};

export function highlightSelection(layers: ReadonlyMap<string, CellLayer>, selectedId: string) {
  for (const [id, layer] of layers) {
    const selected = id === selectedId;
    layer.setStyle({ color: selected ? "#005fcc" : "#52665e", weight: selected ? 4 : 1,
      fillOpacity: selected ? .55 : .3 });
    if (selected) layer.bringToFront();
  }
}
