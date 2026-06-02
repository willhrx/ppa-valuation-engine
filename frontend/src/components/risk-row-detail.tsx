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

  return (
    <div
      className="grid grid-cols-1 gap-6 px-6 py-5 md:grid-cols-3"
      style={{
        background:
          'linear-gradient(180deg, color-mix(in oklch, var(--surface-alt) 60%, transparent), transparent 70%)',
        borderTop: '1px solid var(--border)',
      }}
    >
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
