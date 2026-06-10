// Typed fetch wrappers for the FastAPI backend.
//
// In dev, vite.config.ts proxies /api -> http://localhost:8000. In prod the
// frontend is expected to be served behind the same origin as the API, so
// relative paths work either way and we never need to read VITE_API_BASE.
//
// All payload/response types are derived from `api-types.gen.ts`, which is
// regenerated from `backend/openapi.json` via `npm run gen:types`. The flow:
//
//   backend Pydantic models  ->  scripts/export_openapi.py  ->  openapi.json
//                            ->  openapi-typescript          ->  api-types.gen.ts
//                            ->  (this file)                 ->  components & UI
//
// A schema drift between backend and frontend becomes a compile error here.

import type { components } from './api-types.gen'

type Schemas = components['schemas']

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `API error ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    signal,
    ...init,
  })
  if (!response.ok) {
    // Read the body once as text, then try to parse JSON out of it —
    // calling .json() first and falling back to .text() throws
    // "body stream already read" and masks the real error.
    const raw = await response.text()
    let detail: unknown = raw
    try {
      detail = (JSON.parse(raw) as { detail?: unknown })?.detail ?? raw
    } catch {
      // not JSON — keep raw text
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'GET' }, signal)
}

export function apiPost<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(
    path,
    { method: 'POST', body: JSON.stringify(body ?? {}) },
    signal,
  )
}

// ---------------------------------------------------------------------------
// Schemas re-exported from the generated OpenAPI types.
//
// PPAConfig and its sub-configs are marked Required<> because Pydantic models
// every field as `Optional` at the OpenAPI level (each has a default), but the
// engine always returns them populated and the UI relies on that.
// ---------------------------------------------------------------------------

export type LocationConfig = Required<Schemas['LocationConfigSchema']>
export type SolarConfig = Required<Schemas['SolarConfigSchema']>
export type MarketPriceConfig = Required<Schemas['MarketPriceConfigSchema']>
export type ConsumerLoadConfig = Required<Schemas['ConsumerLoadConfigSchema']>
export type DealConfig = Required<Schemas['DealConfigSchema']>
export type PPAConfig = Required<Schemas['PPAConfigSchema']>

export type TimeSeriesPoint = Schemas['TimeSeriesPoint']
export type PreviewResponse = Schemas['PreviewResponse']
export type ProfilesResponse = Schemas['ProfilesResponse']
export type ValuationRow = Schemas['ValuationRowSchema']
export type ValuationMatrixResponse = Schemas['ValuationMatrixResponse']

export type PathDistribution = Schemas['PathDistributionSchema']
export type VarianceDecomposition = Schemas['VarianceDecompositionSchema']
export type ComboRiskSummary = Schemas['ComboRiskSummarySchema']
export type RiskSummary = Schemas['RiskSummarySchema']
export type MonteCarloResponse = Schemas['MonteCarloResponse']

// /api/health returns a free-form dict in the spec; describe it locally.
export interface HealthResponse {
  status: string
  version: string
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  health: (signal?: AbortSignal) => apiGet<HealthResponse>('/api/health', signal),
  configDefaults: (signal?: AbortSignal) =>
    apiGet<PPAConfig>('/api/config/defaults', signal),
  configValidate: (config: PPAConfig, signal?: AbortSignal) =>
    apiPost<PPAConfig>('/api/config/validate', config, signal),
  preview: (config: PPAConfig, signal?: AbortSignal) =>
    apiPost<PreviewResponse>('/api/preview', config, signal),
  profiles: (config: PPAConfig, signal?: AbortSignal) =>
    apiPost<ProfilesResponse>('/api/profiles', config, signal),
  valuationMatrix: (
    config: PPAConfig,
    baseStrike: number,
    signal?: AbortSignal,
  ) =>
    apiPost<ValuationMatrixResponse>(
      '/api/valuation/matrix',
      { config, base_strike: baseStrike },
      signal,
    ),
  simulate: (
    config: PPAConfig,
    baseStrike: number,
    nPaths: number = 500,
    signal?: AbortSignal,
  ) =>
    apiPost<MonteCarloResponse>(
      '/api/simulate',
      { config, base_strike: baseStrike, n_paths: nPaths },
      signal,
    ),
}
