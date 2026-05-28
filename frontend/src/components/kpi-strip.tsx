import { useMemo } from 'react'

import { api, type PPAConfig, type ValuationMatrixResponse } from '@/lib/api'
import { useAsyncCall } from '@/hooks/useAsync'

interface KpiStripProps {
  config: PPAConfig | null
  baseStrike: number
}

interface KpiCardProps {
  label: string
  labelColor: string
  ringColor: string
  bgWash: string
  fgWash: string
  children: React.ReactNode
  topRight?: React.ReactNode
  loading?: boolean
}

function KpiCard({
  label,
  labelColor,
  ringColor,
  bgWash,
  fgWash,
  children,
  topRight,
  loading,
}: KpiCardProps) {
  return (
    <div
      className="relative overflow-hidden rounded-xl border bg-card px-5 py-4 shadow-[0_1px_0_rgba(20,14,6,0.025),0_1px_3px_rgba(20,14,6,0.04)]"
      style={{
        background: `linear-gradient(155deg, ${bgWash} 0%, var(--card) 65%)`,
        borderColor: ringColor,
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 -right-10 h-32 w-32 rounded-full"
        style={{
          background: `radial-gradient(circle, ${fgWash}22 0%, transparent 70%)`,
        }}
      />
      <div className="relative">
        <div className="mb-2.5 flex items-center justify-between">
          <span
            className="text-[10.5px] font-bold tracking-[0.09em] uppercase"
            style={{ color: labelColor }}
          >
            {label}
          </span>
          {topRight}
        </div>
        {loading ? (
          <div className="space-y-2">
            <div className="h-9 w-32 animate-pulse rounded bg-muted" />
            <div className="h-4 w-24 animate-pulse rounded bg-muted" />
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  )
}

function PillBadge({
  children,
  bg,
  fg,
}: {
  children: React.ReactNode
  bg: string
  fg: string
}) {
  return (
    <span
      className="rounded-full px-1.5 py-0.5 font-mono text-[10px] font-semibold tabular-nums"
      style={{ background: bg, color: fg }}
    >
      {children}
    </span>
  )
}

export function KpiStrip({ config, baseStrike }: KpiStripProps) {
  const { state } = useAsyncCall<ValuationMatrixResponse>(
    (signal) => {
      if (!config) return Promise.reject(new Error('no config'))
      return api.valuationMatrix(config, baseStrike, signal)
    },
    [config, baseStrike],
  )

  const stats = useMemo(() => {
    if (state.status !== 'success') return null
    const rows = state.data.rows
    if (rows.length === 0) return null
    const npvs = rows.map((r) => r.producer_npv)
    const strikes = rows.map((r) => r.average_strike_eur_mwh)
    const captures = rows.map((r) => r.capture_rate)
    const profiles = rows.map((r) => r.profile_value)
    const npvMin = Math.min(...npvs)
    const npvMax = Math.max(...npvs)
    const npvMed = npvs.slice().sort((a, b) => a - b)[Math.floor(npvs.length / 2)]
    const strikeMin = Math.min(...strikes)
    const strikeMax = Math.max(...strikes)
    const captureMax = Math.max(...captures)
    const profileMin = Math.min(...profiles)
    return {
      npvMin,
      npvMax,
      npvMed,
      strikeMin,
      strikeMax,
      captureMax,
      profileMin,
      sparkline: npvs,
    }
  }, [state])

  const loading = state.status === 'loading' || state.status === 'idle'
  const fmtM = (v: number) =>
    `${v < 0 ? '−' : ''}€${(Math.abs(v) / 1e6).toFixed(2)}M`

  return (
    <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
      {/* NPV — accent tinted */}
      <KpiCard
        label="Producer NPV · best"
        labelColor="var(--accent-deep)"
        ringColor="color-mix(in oklch, var(--accent) 25%, transparent)"
        bgWash="var(--accent-soft)"
        fgWash="var(--accent)"
        loading={loading || !stats}
        topRight={
          stats && (
            <PillBadge bg="var(--positive-soft)" fg="var(--positive)">
              ↑ matrix
            </PillBadge>
          )
        }
      >
        {stats && (
          <>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[40px] leading-none font-semibold tracking-[-0.035em] tabular-nums">
                €{(stats.npvMax / 1e6).toFixed(2)}
              </span>
              <span
                className="text-base font-semibold"
                style={{ color: 'var(--accent-deep)' }}
              >
                M
              </span>
            </div>
            <div className="mt-3.5 flex items-center gap-3">
              <Sparkline
                data={stats.sparkline}
                color="var(--accent)"
                width={150}
                height={32}
              />
              <div className="font-mono text-[10px] leading-snug tabular-nums">
                <div className="text-muted-foreground">
                  min{' '}
                  <span className="font-semibold text-foreground">
                    {fmtM(stats.npvMin)}
                  </span>
                </div>
                <div className="text-muted-foreground">
                  med{' '}
                  <span className="font-semibold text-foreground">
                    {fmtM(stats.npvMed)}
                  </span>
                </div>
              </div>
            </div>
          </>
        )}
      </KpiCard>

      {/* Capture — solar tinted */}
      <KpiCard
        label="Capture rate · best"
        labelColor="var(--solar-deep)"
        ringColor="color-mix(in oklch, var(--solar-deep) 22%, transparent)"
        bgWash="var(--solar-soft)"
        fgWash="var(--solar)"
        loading={loading || !stats}
        topRight={
          <span className="font-mono text-[10px] text-muted-foreground">
            Δ vs baseload
          </span>
        }
      >
        {stats && (
          <>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[40px] leading-none font-semibold tracking-[-0.035em] tabular-nums">
                {(stats.captureMax * 100).toFixed(1)}
              </span>
              <span
                className="text-lg font-semibold"
                style={{ color: 'var(--solar-deep)' }}
              >
                %
              </span>
              <span
                className="ml-auto font-mono text-xs font-semibold tabular-nums"
                style={{ color: 'var(--negative)' }}
              >
                −{((1 - stats.captureMax) * 100).toFixed(1)} pp
              </span>
            </div>
            <div className="mt-3.5">
              <div className="relative h-2.5 overflow-hidden rounded border bg-card">
                <div
                  className="absolute inset-y-0 left-0 rounded"
                  style={{
                    width: `${stats.captureMax * 100}%`,
                    background:
                      'linear-gradient(90deg, var(--solar), var(--accent))',
                    boxShadow: '0 0 8px color-mix(in oklch, var(--accent) 25%, transparent)',
                  }}
                />
              </div>
              <div className="mt-1.5 flex justify-between font-mono text-[10px] text-muted-foreground tabular-nums">
                <span>0%</span>
                <span>floor 65%</span>
                <span
                  className="font-semibold"
                  style={{ color: 'var(--solar-deep)' }}
                >
                  100%
                </span>
              </div>
            </div>
          </>
        )}
      </KpiCard>

      {/* Negotiation — price tinted */}
      <KpiCard
        label="Negotiation range"
        labelColor="var(--price-deep)"
        ringColor="color-mix(in oklch, var(--price) 22%, transparent)"
        bgWash="var(--price-soft)"
        fgWash="var(--price)"
        loading={loading || !stats}
        topRight={
          <span className="font-mono text-[10px] text-muted-foreground">
            €/MWh
          </span>
        }
      >
        {stats && (
          <>
            <div className="flex items-baseline gap-2">
              <span
                className="font-mono text-[30px] leading-none font-semibold tracking-[-0.03em] tabular-nums"
                style={{ color: 'var(--accent)' }}
              >
                {stats.strikeMin.toFixed(1)}
              </span>
              <span className="text-xs text-muted-foreground">→</span>
              <span
                className="font-mono text-[30px] leading-none font-semibold tracking-[-0.03em] tabular-nums"
                style={{ color: 'var(--price)' }}
              >
                {stats.strikeMax.toFixed(1)}
              </span>
              <span className="ml-auto font-mono text-[11px] text-muted-foreground tabular-nums">
                spread{' '}
                <span className="font-semibold text-foreground">
                  €{(stats.strikeMax - stats.strikeMin).toFixed(1)}
                </span>
              </span>
            </div>
            <div className="mt-3.5">
              <div className="relative h-2.5 rounded border bg-card">
                <div
                  className="absolute rounded"
                  style={{
                    left: '25%',
                    width: '40%',
                    top: -1,
                    bottom: -1,
                    background:
                      'linear-gradient(90deg, var(--accent), var(--price))',
                    opacity: 0.85,
                  }}
                />
                <div
                  className="absolute top-[-4px] bottom-[-4px] w-[3px] rounded-sm"
                  style={{ left: 'calc(25% - 1px)', background: 'var(--accent)' }}
                />
                <div
                  className="absolute top-[-4px] bottom-[-4px] w-[3px] rounded-sm"
                  style={{ left: 'calc(65% - 1px)', background: 'var(--price)' }}
                />
              </div>
              <div className="mt-1.5 flex justify-between font-mono text-[10px] tabular-nums">
                <span
                  className="font-semibold"
                  style={{ color: 'var(--accent-deep)' }}
                >
                  floor
                </span>
                <span className="text-muted-foreground">negotiation zone</span>
                <span
                  className="font-semibold"
                  style={{ color: 'var(--price-deep)' }}
                >
                  ceiling
                </span>
              </div>
            </div>
          </>
        )}
      </KpiCard>

      {/* Profile risk — load tinted */}
      <KpiCard
        label="Profile risk · worst"
        labelColor="var(--load-deep)"
        ringColor="color-mix(in oklch, var(--load) 22%, transparent)"
        bgWash="var(--load-soft)"
        fgWash="var(--load)"
        loading={loading || !stats}
        topRight={
          <span className="font-mono text-[10px] text-muted-foreground">
            matrix attrib.
          </span>
        }
      >
        {stats && (
          <>
            <div className="flex items-baseline gap-1.5">
              <span
                className="font-mono text-[40px] leading-none font-semibold tracking-[-0.035em] tabular-nums"
                style={{
                  color:
                    stats.profileMin < 0
                      ? 'var(--negative)'
                      : 'var(--positive)',
                }}
              >
                {fmtM(stats.profileMin)}
              </span>
            </div>
            <div className="mt-3.5 flex flex-col gap-1">
              {[
                { l: 'Price', v: 62, c: 'var(--price)' },
                { l: 'Volume', v: 24, c: 'var(--solar)' },
                { l: 'Profile', v: 14, c: 'var(--load)' },
              ].map((r) => (
                <div
                  key={r.l}
                  className="flex items-center gap-2 text-[10.5px]"
                >
                  <span className="w-11 font-mono text-muted-foreground">
                    {r.l}
                  </span>
                  <div className="h-1 flex-1 overflow-hidden rounded-sm border bg-card">
                    <div
                      className="h-full rounded-sm"
                      style={{ width: `${r.v}%`, background: r.c }}
                    />
                  </div>
                  <span className="min-w-[30px] text-right font-mono font-semibold tabular-nums">
                    {r.v}%
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </KpiCard>
    </div>
  )
}

function Sparkline({
  data,
  color,
  width,
  height,
}: {
  data: number[]
  color: string
  width: number
  height: number
}) {
  if (data.length < 2) {
    return <div style={{ width, height }} />
  }
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const px = (i: number) => (i / (data.length - 1)) * width
  const py = (v: number) => height - 2 - ((v - min) / range) * (height - 4)
  const line = data
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${px(i).toFixed(1)} ${py(v).toFixed(1)}`)
    .join(' ')
  const area = `${line} L ${width} ${height} L 0 ${height} Z`
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      style={{ width, height, display: 'block' }}
    >
      <path d={area} fill={color} opacity={0.18} />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={1.4}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <line
        x1={width * 0.5}
        x2={width * 0.5}
        y1={4}
        y2={height - 2}
        stroke={color}
        strokeWidth={1}
        strokeDasharray="2 2"
        opacity={0.6}
      />
    </svg>
  )
}
