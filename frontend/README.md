# PPA Valuation Engine — frontend

Single-page Vite + React 19 + TypeScript dashboard for the PPA valuation
backend. Designed as a dense, desk-side analysis surface — not a multi-step
wizard.

## Dev workflow

```bash
npm install
npm run gen:types     # regenerate src/lib/api-types.gen.ts from backend OpenAPI
npm run dev           # http://localhost:5173, proxies /api → http://localhost:8000
npm run build         # tsc -b && vite build → ./dist
npm run lint
```

The dev server proxy is configured in `vite.config.ts` so relative `/api`
paths work in both dev and prod (where the frontend is expected to be
served behind the same origin as the FastAPI backend).

Whenever the backend Pydantic schemas change, re-run `gen:types` so the
generated `src/lib/api-types.gen.ts` stays in sync — schema drift becomes a
TypeScript compile error in `src/lib/api.ts`.

## Folder map

```text
src/
├── App.tsx                     # Layout shell, top nav, lifted simulation state
├── main.tsx                    # ReactDOM root
├── index.css                   # OKLch theme tokens (light + dark)
├── components/
│   ├── ui/                     # shadcn primitives (button, card, slider, table, …)
│   ├── kpi-strip.tsx           # Top KPI cards + sparkline + attribution
│   ├── config-panel.tsx        # Sticky left config panel (location map + sliders)
│   ├── location-map.tsx        # MapLibre wrapper, draggable pin, lat/lon binding
│   ├── profiles-charts.tsx     # Recharts ComposedChart (Solar + Load + Spot)
│   ├── valuation-matrix-table.tsx  # TanStack table, expand-in-row for risk
│   ├── risk-row-detail.tsx     # Per-combo P10/P50/P90, VaR/ES, variance bar
│   └── spinner.tsx             # PanelLoading / PanelError
├── hooks/
│   ├── useAsync.ts             # Generic deps-reactive async wrapper
│   └── useRiskSimulation.ts    # /api/simulate state (lifted at App level)
└── lib/
    ├── api.ts                  # Typed fetch wrappers, endpoint definitions
    ├── api-types.gen.ts        # Auto-generated from backend/openapi.json
    ├── downsample.ts           # Hourly → daily aggregation, sample-week slice
    ├── format.ts               # Currency / energy / percent formatters
    └── utils.ts                # cn() class-name helper
```

## Theming

All semantic colors live as OKLch variables in `src/index.css`:

| Variable | Use |
| --- | --- |
| `--solar` / `-soft` / `-deep` | Solar generation, pay-as-produced supply |
| `--load` / `-soft` / `-deep` | Offtaker load, pay-as-nominated supply, volume risk |
| `--price` / `-soft` / `-deep` | Day-ahead price, baseload supply, price risk |
| `--accent` / `-soft` / `-deep` | CTAs, "best" highlights, focused state |
| `--positive` / `--negative` (+ `-soft`) | Profile value & risk tone |

Never hard-code colors in components. Use `var(--token)` and the variants
so dark mode (handled by the `.dark` overrides at the bottom of
`index.css`) keeps working.

Typography is Geist Variable (body) with tabular-nums monospace for all
numeric cells.

## Where to add a new chart

1. Create the component under `src/components/your-chart.tsx`.
2. Pull theme colors via `var(--solar | load | price | accent)` — keep
   tooltip/grid/axis styling consistent with `profiles-charts.tsx`.
3. Wrap chart data fetching in `useAsyncCall` from `@/hooks/useAsync` so
   the loading/error states match the rest of the dashboard.
4. Mount the component inside `App.tsx` with a `<div id="…" className="scroll-mt-20">`
   wrapper so the top-nav anchor link can target it.

## Where to add a new API call

1. Add (or update) the backend Pydantic schema, then run
   `python scripts/export_openapi.py` and `npm run gen:types`.
2. Re-export the new schema as a typed alias from `src/lib/api.ts`.
3. Add an `api.<name>(...)` wrapper next to the existing endpoints in the
   same file — use `apiGet` / `apiPost` so errors flow through `ApiError`.
4. Consume in a component via `useAsyncCall` (for request-on-deps-change
   patterns) or follow `useRiskSimulation` for explicit-trigger flows.

## Map tiles & attribution

`location-map.tsx` uses raster tiles from OpenStreetMap directly. The OSM
Tile Usage Policy **requires the attribution string be visible** —
`© OpenStreetMap contributors` is already wired into the MapLibre style
spec; if you swap tile providers (Stadia, Carto, MapTiler, etc.), update
the `attribution` field in `OSM_STYLE` to match the new provider's terms.

Dark mode caveat: OSM raster tiles are light-only. The rest of the UI
adapts via the OKLch dark theme, but the map will remain bright until we
switch to a vector basemap.

## State management

No global store — `App.tsx` owns the applied `PPAConfig` and the lifted
`useRiskSimulation` handle, and passes them down. Components fetch their
own data via `useAsyncCall` against the same `applied.config` so cache
invalidation is trivially "the config object reference changed".

This is fine for the current surface area. If a third sibling needs the
risk results, lift further (don't introduce a store reflexively).
