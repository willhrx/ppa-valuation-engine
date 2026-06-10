import { useMemo } from 'react'

import type { ComboRiskSummary } from '@/lib/api'
import { fmtEurMillion, fmtPercent } from '@/lib/format'
import { cn } from '@/lib/utils'

interface RiskRowDetailProps {
  combo: ComboRiskSummary
}

export function RiskRowDetail({ combo }: RiskRowDetailProps) {
  const { joint, variance_decomp } = combo
  const priceShare = variance_decomp.price_share
  const volumeShare = variance_decomp.volume_share
  const interactionShare = variance_decomp.interaction_share

  const probAlert = joint.prob_negative > 0.2

  const hasNpvArrays =
    combo.npvs_joint.length > 0 &&
    combo.npvs_price.length > 0 &&
    combo.npvs_volume.length > 0

  return (
    <div
      className="px-6 py-5"
      style={{
        background:
          'linear-gradient(180deg, color-mix(in oklch, var(--surface-alt) 60%, transparent), transparent 70%)',
        borderTop: '1px solid var(--border)',
      }}
    >
      {hasNpvArrays && (
        <div className="mb-5">
          <SectionLabel>
            Producer NPV distribution · joint vs price-only vs volume-only
          </SectionLabel>
          <NpvHistogram
            joint={combo.npvs_joint}
            price={combo.npvs_price}
            volume={combo.npvs_volume}
            p10={joint.p10}
            p50={joint.p50}
            p90={joint.p90}
          />
        </div>
      )}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
      <DistributionPanel
        title="NPV distribution"
        rows={[
          { label: 'P10 (downside)', value: joint.p10, accent: joint.p10 < 0 },
          { label: 'P50 (median)', value: joint.p50 },
          { label: 'P90 (upside)', value: joint.p90 },
          { label: 'Mean', value: joint.mean, muted: true },
          { label: 'σ', value: joint.std, muted: true, raw: true },
        ]}
      />

      <TailRiskPanel
        var95={joint.var_95}
        es95={joint.es_95}
        probNeg={joint.prob_negative}
        probAlert={probAlert}
      />

      <VarianceAttributionPanel
        price={priceShare}
        volume={volumeShare}
        interaction={interactionShare}
      />
      </div>
    </div>
  )
}

const HIST_BINS = 36
const HIST_W = 720
const HIST_H = 120

const HIST_SERIES: Array<{
  key: 'joint' | 'price' | 'volume'
  label: string
  color: string
}> = [
  { key: 'price', label: 'price-only', color: 'var(--price)' },
  { key: 'volume', label: 'volume-only', color: 'var(--load)' },
  { key: 'joint', label: 'joint', color: 'var(--accent)' },
]

function NpvHistogram({
  joint,
  price,
  volume,
  p10,
  p50,
  p90,
}: {
  joint: number[]
  price: number[]
  volume: number[]
  p10: number
  p50: number
  p90: number
}) {
  const model = useMemo(() => {
    const all = [...joint, ...price, ...volume]
    const lo = Math.min(...all)
    const hi = Math.max(...all)
    const span = Math.max(hi - lo, 1)
    const counts = { joint, price, volume } as const
    const bins: Record<string, number[]> = {}
    let maxCount = 1
    for (const { key } of HIST_SERIES) {
      const b = new Array<number>(HIST_BINS).fill(0)
      for (const v of counts[key]) {
        const i = Math.min(
          HIST_BINS - 1,
          Math.floor(((v - lo) / span) * HIST_BINS),
        )
        b[i] += 1
      }
      bins[key] = b
      maxCount = Math.max(maxCount, ...b)
    }
    const x = (v: number) => ((v - lo) / span) * HIST_W
    return { lo, hi, bins, maxCount, x }
  }, [joint, price, volume])

  const binW = HIST_W / HIST_BINS
  const zeroInRange = model.lo < 0 && model.hi > 0

  return (
    <div className="mt-2">
      <svg
        viewBox={`0 0 ${HIST_W} ${HIST_H}`}
        preserveAspectRatio="none"
        className="h-[120px] w-full rounded-md border bg-card"
        role="img"
        aria-label="Producer NPV histogram across Monte Carlo ensembles"
      >
        {HIST_SERIES.map(({ key, color }) => (
          <g key={key} fill={color} fillOpacity={key === 'joint' ? 0.55 : 0.35}>
            {model.bins[key].map((c, i) =>
              c > 0 ? (
                <rect
                  key={i}
                  x={i * binW}
                  y={HIST_H - (c / model.maxCount) * (HIST_H - 8)}
                  width={Math.max(binW - 1, 1)}
                  height={(c / model.maxCount) * (HIST_H - 8)}
                />
              ) : null,
            )}
          </g>
        ))}
        {zeroInRange && (
          <line
            x1={model.x(0)}
            x2={model.x(0)}
            y1={0}
            y2={HIST_H}
            stroke="var(--negative)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        )}
        {[
          { v: p10, label: 'P10' },
          { v: p50, label: 'P50' },
          { v: p90, label: 'P90' },
        ].map(({ v, label }) => (
          <g key={label}>
            <line
              x1={model.x(v)}
              x2={model.x(v)}
              y1={10}
              y2={HIST_H}
              stroke="var(--foreground)"
              strokeWidth={1}
              strokeOpacity={0.5}
            />
            <text
              x={model.x(v) + 3}
              y={9}
              fontSize={9}
              fill="var(--muted-foreground)"
              fontFamily="ui-monospace, monospace"
            >
              {label}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-1.5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          {HIST_SERIES.map(({ key, label, color }) => (
            <span
              key={key}
              className="inline-flex items-center gap-1.5 text-[10.5px]"
              style={{ color: 'var(--text-soft)' }}
            >
              <span
                className="inline-block h-2 w-2 rounded-[3px]"
                style={{ background: color, opacity: key === 'joint' ? 0.85 : 0.55 }}
              />
              {label}
            </span>
          ))}
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">
          {fmtEurMillion(model.lo)} … {fmtEurMillion(model.hi)}
        </span>
      </div>
    </div>
  )
}

interface DistRow {
  label: string
  value: number
  accent?: boolean
  muted?: boolean
  raw?: boolean
}

function DistributionPanel({ title, rows }: { title: string; rows: DistRow[] }) {
  return (
    <div>
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-2 divide-y divide-[color:var(--border)] overflow-hidden rounded-md border bg-card">
        {rows.map((r) => (
          <div
            key={r.label}
            className="flex items-baseline justify-between px-3 py-2"
          >
            <span
              className="text-[11px]"
              style={{
                color: r.muted
                  ? 'var(--muted-foreground)'
                  : 'var(--text-soft)',
              }}
            >
              {r.label}
            </span>
            <span
              className={cn(
                'font-mono text-[12px] font-semibold tabular-nums',
                r.accent && 'text-[color:var(--negative)]',
              )}
              style={r.muted ? { color: 'var(--muted-foreground)' } : undefined}
            >
              {r.raw
                ? r.value.toLocaleString('en-IE', { maximumFractionDigits: 0 })
                : fmtEurMillion(r.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function TailRiskPanel({
  var95,
  es95,
  probNeg,
  probAlert,
}: {
  var95: number
  es95: number
  probNeg: number
  probAlert: boolean
}) {
  return (
    <div>
      <SectionLabel>Tail risk</SectionLabel>
      <div className="mt-2 space-y-2">
        <MetricRow
          label="VaR (95%)"
          value={fmtEurMillion(var95)}
          hint="5% worst-case loss threshold"
        />
        <MetricRow
          label="ES (95%)"
          value={fmtEurMillion(es95)}
          hint="Average loss in the worst 5%"
        />
        <div
          className="flex items-baseline justify-between rounded-md border px-3 py-2"
          style={
            probAlert
              ? {
                  background: 'var(--negative-soft)',
                  borderColor:
                    'color-mix(in oklch, var(--negative) 25%, transparent)',
                }
              : { background: 'var(--card)' }
          }
        >
          <span
            className="text-[11px]"
            style={{
              color: probAlert ? 'var(--negative)' : 'var(--text-soft)',
            }}
          >
            P(NPV &lt; 0)
          </span>
          <span
            className="font-mono text-[12px] font-semibold tabular-nums"
            style={{
              color: probAlert ? 'var(--negative)' : 'var(--foreground)',
            }}
          >
            {fmtPercent(probNeg)}
          </span>
        </div>
      </div>
    </div>
  )
}

function MetricRow({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="flex items-baseline justify-between rounded-md border bg-card px-3 py-2">
      <div className="flex flex-col">
        <span
          className="text-[11px]"
          style={{ color: 'var(--text-soft)' }}
        >
          {label}
        </span>
        {hint && (
          <span className="text-[10px] text-muted-foreground">{hint}</span>
        )}
      </div>
      <span className="font-mono text-[12px] font-semibold tabular-nums">
        {value}
      </span>
    </div>
  )
}

function VarianceAttributionPanel({
  price,
  volume,
  interaction,
}: {
  price: number
  volume: number
  interaction: number
}) {
  // price_share / volume_share / interaction_share sum to ~1.0 by definition,
  // but interaction_share can be negative when price and volume offset
  // (cov(price,volume) < 0). Display *signed* percentages in the legend, and
  // normalise by the L1 norm so the bar always fills exactly 100% — the bar
  // shows magnitude of contribution, the legend preserves the sign.
  const pricePct = price * 100
  const volumePct = volume * 100
  const interactionPct = interaction * 100
  const l1 = Math.max(
    1e-9,
    Math.abs(price) + Math.abs(volume) + Math.abs(interaction),
  )
  const priceWidth = (Math.abs(price) / l1) * 100
  const volumeWidth = (Math.abs(volume) / l1) * 100
  const interactionWidth = (Math.abs(interaction) / l1) * 100

  return (
    <div>
      <SectionLabel>Variance attribution</SectionLabel>
      <p className="mt-1 text-[10.5px] text-muted-foreground">
        Share of NPV variance from each driver. Negative interaction means
        price and volume risks partly offset.
      </p>
      <div
        className="mt-3 flex h-3 w-full overflow-hidden rounded-full"
        style={{ background: 'var(--surface-alt)' }}
      >
        <div style={{ width: `${priceWidth}%`, background: 'var(--price)' }} />
        <div style={{ width: `${volumeWidth}%`, background: 'var(--load)' }} />
        <div
          style={{
            width: `${interactionWidth}%`,
            background: 'var(--text-soft)',
            opacity: interaction < 0 ? 0.45 : 1,
          }}
        />
      </div>
      <div className="mt-2 flex flex-col gap-1">
        <AttributionRow color="var(--price)" label="Price" pct={pricePct} />
        <AttributionRow color="var(--load)" label="Volume" pct={volumePct} />
        <AttributionRow
          color="var(--text-soft)"
          label="Interaction"
          pct={interactionPct}
        />
      </div>
    </div>
  )
}

function AttributionRow({
  color,
  label,
  pct,
}: {
  color: string
  label: string
  pct: number
}) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="inline-flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ background: color }}
        />
        <span style={{ color: 'var(--text-soft)' }}>{label}</span>
      </span>
      <span
        className="font-mono font-semibold tabular-nums"
        style={pct < 0 ? { color: 'var(--text-soft)' } : undefined}
      >
        {pct >= 0 ? '' : '−'}
        {Math.abs(pct).toFixed(1)}%
      </span>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="text-[10px] font-bold tracking-[0.08em] uppercase"
      style={{ color: 'var(--muted-foreground)' }}
    >
      {children}
    </span>
  )
}
