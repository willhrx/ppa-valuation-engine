import { useCallback, useRef, useState } from 'react'

import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PanelError } from '@/components/spinner'
import {
  ApiError,
  api,
  type FairStrikeResult,
  type NegotiationRangeResponse,
  type PPAConfig,
  type PricingKey,
  type SupplyKey,
  type TornadoResult,
} from '@/lib/api'
import { fmtEurMillion, fmtEurPerMwh } from '@/lib/format'

interface SolverPanelProps {
  config: PPAConfig | null
  baseStrike: number
}

const SUPPLY_OPTIONS: Array<{ key: SupplyKey; label: string }> = [
  { key: 'pay_as_produced', label: 'Pay-as-produced' },
  { key: 'pay_as_nominated', label: 'Pay-as-nominated' },
  { key: 'baseload', label: 'Baseload' },
]

const PRICING_OPTIONS: Array<{ key: PricingKey; label: string }> = [
  { key: 'fixed_flat', label: 'Fixed flat' },
  { key: 'fixed_escalated', label: 'Fixed escalated' },
  { key: 'indexed_with_floor_cap', label: 'Indexed + floor/cap' },
  { key: 'floating', label: 'Floating' },
]

const SUPPLY_LABEL: Record<string, string> = {
  pay_as_produced: 'Pay-as-produced',
  pay_as_nominated: 'Pay-as-nominated',
  baseload: 'Baseload',
  PayAsProduced: 'Pay-as-produced',
  PayAsNominated: 'Pay-as-nominated',
  Baseload: 'Baseload',
}

// On-demand call: nothing fires until the user clicks run. Tracks the config
// identity at launch so results can be flagged stale after a new Apply.
type ManualState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T; ranWith: PPAConfig }
  | { status: 'error'; message: string }

function useManualCall<T>() {
  const [state, setState] = useState<ManualState<T>>({ status: 'idle' })
  const tick = useRef(0)
  const run = useCallback(
    (config: PPAConfig, fn: (signal: AbortSignal) => Promise<T>) => {
      const controller = new AbortController()
      const myTick = ++tick.current
      setState({ status: 'loading' })
      fn(controller.signal).then(
        (data) => {
          if (myTick === tick.current)
            setState({ status: 'success', data, ranWith: config })
        },
        (err: unknown) => {
          if (myTick !== tick.current) return
          const message =
            err instanceof ApiError
              ? `${err.status}: ${String(err.detail ?? err.message)}`
              : err instanceof Error
                ? err.message
                : 'Unknown error'
          setState({ status: 'error', message })
        },
      )
    },
    [],
  )
  return { state, run }
}

function StaleHint({ ranWith, config }: { ranWith: PPAConfig; config: PPAConfig | null }) {
  if (config === null || ranWith === config) return null
  return (
    <p
      className="mt-2 font-mono text-[10.5px]"
      style={{ color: 'var(--negative)' }}
    >
      ⚠ config changed since this run — results refer to the previous setup
    </p>
  )
}

function RunButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-[7px] border px-3 py-1.5 text-[11.5px] font-semibold text-primary-foreground transition-shadow hover:shadow disabled:cursor-not-allowed disabled:opacity-50"
      style={{
        background: 'linear-gradient(180deg, var(--accent), var(--accent-deep))',
        borderColor: 'var(--accent-deep)',
      }}
    >
      {children}
    </button>
  )
}

function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: Array<{ key: T; label: string }>
  onChange: (v: T) => void
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="rounded-[6px] border bg-transparent px-1.5 py-1 font-mono text-[11px] text-foreground"
      >
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function SolverPanel({ config, baseStrike }: SolverPanelProps) {
  return (
    <Card className="p-0">
      <div className="border-b px-6 pt-5 pb-4">
        <div className="text-sm font-semibold tracking-[-0.005em]">
          Pricing solver
        </div>
        <p className="mt-1 text-[11.5px] text-muted-foreground">
          Break-even analysis on the central scenario — negotiation range,
          assumption sensitivity, and cross-structure fair strikes. Each tool
          runs on demand.
        </p>
      </div>
      <CardContent className="px-6 py-4">
        <Tabs defaultValue="range" className="w-full">
          <TabsList className="rounded-[9px] bg-muted p-1">
            <TabsTrigger value="range" className="text-[11.5px]">
              Negotiation range
            </TabsTrigger>
            <TabsTrigger value="tornado" className="text-[11.5px]">
              Tornado sensitivity
            </TabsTrigger>
            <TabsTrigger value="fair" className="text-[11.5px]">
              Fair strike
            </TabsTrigger>
          </TabsList>

          <TabsContent value="range" className="pt-4">
            <NegotiationRangeTool config={config} />
          </TabsContent>
          <TabsContent value="tornado" className="pt-4">
            <TornadoTool config={config} baseStrike={baseStrike} />
          </TabsContent>
          <TabsContent value="fair" className="pt-4">
            <FairStrikeTool config={config} baseStrike={baseStrike} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Negotiation range
// ---------------------------------------------------------------------------

function NegotiationRangeTool({ config }: { config: PPAConfig | null }) {
  const { state, run } = useManualCall<NegotiationRangeResponse>()
  const [targetNpv, setTargetNpv] = useState(0)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
          producer target NPV (€M)
          <input
            type="number"
            value={targetNpv}
            step={0.5}
            onChange={(e) => setTargetNpv(Number(e.target.value))}
            className="w-20 rounded-[6px] border bg-transparent px-1.5 py-1 font-mono text-[11px] text-foreground"
          />
        </label>
        <RunButton
          disabled={!config || state.status === 'loading'}
          onClick={() =>
            config &&
            run(config, (signal) =>
              api.solverNegotiationRange(config, targetNpv * 1e6, signal),
            )
          }
        >
          {state.status === 'loading'
            ? 'Solving…'
            : 'Solve range · ~10 s'}
        </RunButton>
      </div>
      <p className="mt-1.5 text-[10.5px] text-muted-foreground">
        Producer floor = fixed-flat strike where the producer hits the target
        NPV; consumer ceiling = strike where the consumer breaks even vs spot.
        The spread between them is the negotiable zone.
      </p>

      {state.status === 'error' && (
        <div className="mt-3">
          <PanelError message={state.message} />
        </div>
      )}
      {state.status === 'success' && (
        <div className="mt-4 space-y-3">
          <RangeBars data={state.data} />
          <StaleHint ranWith={state.ranWith} config={config} />
        </div>
      )}
    </div>
  )
}

function RangeBars({ data }: { data: NegotiationRangeResponse }) {
  const ranges = data.ranges
  const lo = Math.min(...ranges.map((r) => r.producer_floor.strike_eur_mwh))
  const hi = Math.max(...ranges.map((r) => r.consumer_ceiling.strike_eur_mwh))
  const span = Math.max(hi - lo, 1)
  const pad = span * 0.1
  const x = (v: number) => ((v - lo + pad) / (span + 2 * pad)) * 100

  return (
    <div className="space-y-2.5">
      {ranges.map((r) => {
        const floor = r.producer_floor.strike_eur_mwh
        const ceil = r.consumer_ceiling.strike_eur_mwh
        return (
          <div key={r.supply_structure}>
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-[11.5px] font-medium">
                {SUPPLY_LABEL[r.supply_structure] ?? r.supply_structure}
              </span>
              <span className="font-mono text-[10.5px] text-muted-foreground">
                {fmtEurPerMwh(floor)} → {fmtEurPerMwh(ceil)} · spread{' '}
                {fmtEurPerMwh(r.spread_eur_mwh)} · mid {fmtEurPerMwh(r.midpoint)}
              </span>
            </div>
            <div
              className="relative h-4 w-full overflow-hidden rounded-full"
              style={{ background: 'var(--surface-alt)' }}
            >
              <div
                className="absolute top-0 h-full rounded-full"
                style={{
                  left: `${x(floor)}%`,
                  width: `${Math.max(x(ceil) - x(floor), 0.5)}%`,
                  background:
                    'linear-gradient(90deg, var(--accent), var(--solar-deep))',
                  opacity: 0.75,
                }}
              />
              <div
                className="absolute top-0 h-full w-[2px]"
                style={{ left: `${x(r.midpoint)}%`, background: 'var(--foreground)' }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tornado
// ---------------------------------------------------------------------------

function TornadoTool({
  config,
  baseStrike,
}: {
  config: PPAConfig | null
  baseStrike: number
}) {
  const { state, run } = useManualCall<TornadoResult>()
  const [supply, setSupply] = useState<SupplyKey>('pay_as_produced')
  const [pricing, setPricing] = useState<PricingKey>('fixed_flat')

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <SelectField
          label="supply"
          value={supply}
          options={SUPPLY_OPTIONS}
          onChange={setSupply}
        />
        <SelectField
          label="pricing"
          value={pricing}
          options={PRICING_OPTIONS}
          onChange={setPricing}
        />
        <RunButton
          disabled={!config || state.status === 'loading'}
          onClick={() =>
            config &&
            run(config, (signal) =>
              api.solverTornado(config, supply, pricing, baseStrike, signal),
            )
          }
        >
          {state.status === 'loading' ? 'Computing…' : 'Run tornado · ~30 s'}
        </RunButton>
      </div>
      <p className="mt-1.5 text-[10.5px] text-muted-foreground">
        Each assumption is perturbed down/up around the central scenario;
        bars show the producer-NPV swing. Longest bars = the assumptions
        worth arguing about.
      </p>

      {state.status === 'error' && (
        <div className="mt-3">
          <PanelError message={state.message} />
        </div>
      )}
      {state.status === 'success' && (
        <div className="mt-4">
          <TornadoBars data={state.data} />
          <StaleHint ranWith={state.ranWith} config={config} />
        </div>
      )}
    </div>
  )
}

function TornadoBars({ data }: { data: TornadoResult }) {
  const entries = data.entries.slice(0, 12)
  const maxDelta = Math.max(
    1,
    ...entries.flatMap((e) => [
      Math.abs(e.delta_npv_low),
      Math.abs(e.delta_npv_high),
    ]),
  )
  const half = (v: number) => (Math.abs(v) / maxDelta) * 50

  return (
    <div className="space-y-1.5">
      <div className="mb-1 text-right font-mono text-[10px] text-muted-foreground">
        ΔNPV vs base {fmtEurMillion(data.entries[0]?.npv_base ?? 0)}
      </div>
      {entries.map((e) => (
        <div key={e.parameter} className="flex items-center gap-3">
          <span
            className="w-56 shrink-0 truncate text-[11px]"
            style={{ color: 'var(--text-soft)' }}
            title={`${e.parameter} · ${e.low_value} → ${e.high_value}`}
          >
            {e.parameter.replace(/^market\.|^solar\.|^load\.|^deal\./, '')}
          </span>
          <div className="relative h-3.5 flex-1">
            <div
              className="absolute top-0 bottom-0 left-1/2 w-px"
              style={{ background: 'var(--border)' }}
            />
            <div
              className="absolute top-0 h-full rounded-l"
              style={{
                right: '50%',
                width: `${half(e.delta_npv_low < 0 ? e.delta_npv_low : Math.min(e.delta_npv_low, 0))}%`,
                background: 'var(--negative)',
                opacity: 0.7,
              }}
            />
            {e.delta_npv_low > 0 && (
              <div
                className="absolute top-0 h-full rounded-r"
                style={{
                  left: '50%',
                  width: `${half(e.delta_npv_low)}%`,
                  background: 'var(--positive)',
                  opacity: 0.45,
                }}
              />
            )}
            <div
              className="absolute top-0 h-full rounded-r"
              style={{
                left: '50%',
                width: `${half(e.delta_npv_high > 0 ? e.delta_npv_high : Math.max(e.delta_npv_high, 0))}%`,
                background: 'var(--positive)',
                opacity: 0.7,
              }}
            />
            {e.delta_npv_high < 0 && (
              <div
                className="absolute top-0 h-full rounded-l"
                style={{
                  right: '50%',
                  width: `${half(e.delta_npv_high)}%`,
                  background: 'var(--negative)',
                  opacity: 0.45,
                }}
              />
            )}
          </div>
          <span className="w-20 shrink-0 text-right font-mono text-[10.5px] text-muted-foreground">
            {fmtEurMillion(e.abs_swing)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fair strike
// ---------------------------------------------------------------------------

function FairStrikeTool({
  config,
  baseStrike,
}: {
  config: PPAConfig | null
  baseStrike: number
}) {
  const { state, run } = useManualCall<FairStrikeResult>()
  const [structureA, setStructureA] = useState<SupplyKey>('pay_as_produced')
  const [structureB, setStructureB] = useState<SupplyKey>('baseload')
  const [pricing, setPricing] = useState<'fixed_flat' | 'fixed_escalated'>(
    'fixed_flat',
  )
  const [strikeA, setStrikeA] = useState(baseStrike)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <SelectField
          label="structure A"
          value={structureA}
          options={SUPPLY_OPTIONS}
          onChange={setStructureA}
        />
        <SelectField
          label="structure B"
          value={structureB}
          options={SUPPLY_OPTIONS}
          onChange={setStructureB}
        />
        <SelectField
          label="pricing"
          value={pricing}
          options={[
            { key: 'fixed_flat' as const, label: 'Fixed flat' },
            { key: 'fixed_escalated' as const, label: 'Fixed escalated' },
          ]}
          onChange={setPricing}
        />
        <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
          strike A (€/MWh)
          <input
            type="number"
            value={strikeA}
            step={1}
            onChange={(e) => setStrikeA(Number(e.target.value))}
            className="w-20 rounded-[6px] border bg-transparent px-1.5 py-1 font-mono text-[11px] text-foreground"
          />
        </label>
        <RunButton
          disabled={
            !config || structureA === structureB || state.status === 'loading'
          }
          onClick={() =>
            config &&
            run(config, (signal) =>
              api.solverFairStrike(
                config,
                structureA,
                structureB,
                pricing,
                strikeA,
                200,
                signal,
              ),
            )
          }
        >
          {state.status === 'loading' ? 'Solving…' : 'Solve fair strike · ~2 min'}
        </RunButton>
      </div>
      <p className="mt-1.5 text-[10.5px] text-muted-foreground">
        Finds the strike for structure B that delivers the same P50 producer
        NPV as structure A at the given strike (200-path Monte Carlo on both).
        The premium between them is the price of the risk transfer.
      </p>

      {state.status === 'error' && (
        <div className="mt-3">
          <PanelError message={state.message} />
        </div>
      )}
      {state.status === 'success' && (
        <div className="mt-4">
          <FairStrikeResultView data={state.data} />
          <StaleHint ranWith={state.ranWith} config={config} />
        </div>
      )}
    </div>
  )
}

function FairStrikeResultView({ data }: { data: FairStrikeResult }) {
  const premium = data.fair_strike_b - data.strike_a
  return (
    <div className="rounded-md border bg-card px-4 py-3">
      <p className="text-[12px]">
        <span className="font-medium">
          {SUPPLY_LABEL[data.structure_a] ?? data.structure_a}
        </span>{' '}
        at{' '}
        <span className="font-mono font-semibold">
          {fmtEurPerMwh(data.strike_a)}
        </span>{' '}
        ≈{' '}
        <span className="font-medium">
          {SUPPLY_LABEL[data.structure_b] ?? data.structure_b}
        </span>{' '}
        at{' '}
        <span className="font-mono font-semibold">
          {fmtEurPerMwh(data.fair_strike_b)}
        </span>
        <span
          className="ml-2 rounded-[5px] px-1.5 py-0.5 font-mono text-[10.5px] font-semibold"
          style={{
            background: premium >= 0 ? 'var(--positive-soft)' : 'var(--negative-soft)',
            color: premium >= 0 ? 'var(--positive)' : 'var(--negative)',
          }}
        >
          {premium >= 0 ? '+' : ''}
          {premium.toFixed(2)} €/MWh premium
        </span>
      </p>
      <p className="mt-1.5 font-mono text-[10.5px] text-muted-foreground">
        P50 NPV A {fmtEurMillion(data.p50_npv_a)} · P50 NPV B{' '}
        {fmtEurMillion(data.p50_npv_b)} · {data.pricing_structure} ·{' '}
        {data.n_paths} paths
      </p>
    </div>
  )
}
