import { useMemo } from 'react'

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PanelError, PanelLoading } from '@/components/spinner'
import {
  api,
  type CaptureTimeline,
  type PPAConfig,
  type ProfilesResponse,
} from '@/lib/api'
import { aggregateToDaily, sliceWindow } from '@/lib/downsample'
import { fmtNumber } from '@/lib/format'
import { useAsyncCall, type AsyncState } from '@/hooks/useAsync'

interface ProfilesChartsProps {
  config: PPAConfig | null
}

const SOLAR_COLOR = 'var(--solar)'
const LOAD_COLOR = 'var(--load)'
const PRICE_COLOR = 'var(--price)'

export function ProfilesCharts({ config }: ProfilesChartsProps) {
  const { state, refetch } = useAsyncCall<ProfilesResponse>(
    (signal) => {
      if (!config) return Promise.reject(new Error('no config'))
      return api.profiles(config, signal)
    },
    [config],
  )
  const { state: captureState } = useAsyncCall<CaptureTimeline>(
    (signal) => {
      if (!config) return Promise.reject(new Error('no config'))
      return api.captureTimeline(config, signal)
    },
    [config],
  )

  return (
    <Card className="p-0">
      <div className="flex items-start justify-between gap-4 border-b px-6 pt-5 pb-4">
        <div>
          <div className="text-sm font-semibold tracking-[-0.005em]">
            Generation, load &amp; price profiles
          </div>
          <p className="mt-1 text-[11.5px] text-muted-foreground">
            Central-scenario hourly series from <code>/api/profiles</code>,
            aggregated client-side.
            {state.status === 'success' && (
              <>
                {' '}
                <span className="font-mono">
                  {state.data.n_hours.toLocaleString()} hours
                </span>{' '}
                · {state.data.timezone}
              </>
            )}
          </p>
        </div>
        {state.status === 'success' && (
          <button
            type="button"
            className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
            onClick={refetch}
          >
            refresh
          </button>
        )}
      </div>

      <CardContent className="px-5 pt-3 pb-5">
        {state.status === 'idle' && (
          <p className="text-xs text-muted-foreground">
            Apply a configuration to load profiles.
          </p>
        )}
        {state.status === 'loading' && (
          <PanelLoading message="Generating 10-year hourly profile (~10–12 s)…" />
        )}
        {state.status === 'error' && <PanelError message={state.message} />}
        {state.status === 'success' && (
          <ChartTabs profiles={state.data} capture={captureState} />
        )}
      </CardContent>
    </Card>
  )
}

interface LegendPillProps {
  color: string
  label: string
  value: string
}

function LegendPill({ color, label, value }: LegendPillProps) {
  return (
    <div className="flex items-center gap-2 rounded-full border bg-card px-2.5 py-1 text-[11px]">
      <span
        className="h-2 w-2 rounded-full"
        style={{
          background: color,
          boxShadow: `0 0 0 3px color-mix(in oklch, ${color} 15%, transparent)`,
        }}
      />
      <span className="font-medium" style={{ color: 'var(--text-soft)' }}>
        {label}
      </span>
      <span className="font-mono text-muted-foreground">{value}</span>
    </div>
  )
}

function ChartTabs({
  profiles,
  capture,
}: {
  profiles: ProfilesResponse
  capture: AsyncState<CaptureTimeline>
}) {
  const daily = useMemo(() => aggregateToDaily(profiles), [profiles])
  const week = useMemo(() => {
    const year = Number(profiles.timestamps[0].slice(0, 4)) + 1
    return sliceWindow(profiles, `${year}-07-07`, 168)
  }, [profiles])

  const dailyMeans = useMemo(() => {
    if (daily.length === 0) return { solar: 0, load: 0, price: 0 }
    const sum = daily.reduce(
      (acc, d) => {
        acc.solar += d.solar_mwh
        acc.load += d.load_mwh
        acc.price += d.market_price_eur_mwh
        return acc
      },
      { solar: 0, load: 0, price: 0 },
    )
    return {
      solar: sum.solar / daily.length,
      load: sum.load / daily.length,
      price: sum.price / daily.length,
    }
  }, [daily])

  return (
    <Tabs defaultValue="overview" className="w-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <TabsList className="rounded-[9px] bg-muted p-1">
          <TabsTrigger value="overview" className="text-[11.5px]">
            Horizon · daily
          </TabsTrigger>
          <TabsTrigger value="week" className="text-[11.5px]">
            Sample week · hourly
          </TabsTrigger>
          <TabsTrigger value="capture" className="text-[11.5px]">
            Capture rate · annual
          </TabsTrigger>
        </TabsList>

        <div className="flex flex-wrap gap-2">
          <LegendPill
            color={SOLAR_COLOR}
            label="Solar generation"
            value={`${fmtNumber(dailyMeans.solar, 0)} MWh/d avg`}
          />
          <LegendPill
            color={LOAD_COLOR}
            label="Offtaker load"
            value={`${fmtNumber(dailyMeans.load, 0)} MWh/d avg`}
          />
          <LegendPill
            color={PRICE_COLOR}
            label="Day-ahead price"
            value={`€${fmtNumber(dailyMeans.price, 1)}/MWh avg`}
          />
        </div>
      </div>

      <TabsContent value="overview" className="pt-4">
        <div className="aspect-[16/6] w-full min-h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={daily}
              margin={{ top: 10, right: 28, left: 0, bottom: 4 }}
            >
              <defs>
                <linearGradient id="bold-solar" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={SOLAR_COLOR} stopOpacity={0.55} />
                  <stop offset="100%" stopColor={SOLAR_COLOR} stopOpacity={0.06} />
                </linearGradient>
                <linearGradient id="bold-load" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={LOAD_COLOR} stopOpacity={0.38} />
                  <stop offset="100%" stopColor={LOAD_COLOR} stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                tickFormatter={(d: string) => d.slice(0, 7)}
                minTickGap={40}
                stroke="var(--border)"
              />
              <YAxis
                yAxisId="energy"
                tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                width={50}
                tickFormatter={(v: number) => fmtNumber(v, 0)}
                stroke="var(--border)"
                label={{
                  value: 'MWh/day',
                  angle: -90,
                  position: 'insideLeft',
                  style: { fontSize: 10, fill: 'var(--muted-foreground)' },
                }}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                width={50}
                tickFormatter={(v: number) => `€${fmtNumber(v, 0)}`}
                stroke="var(--border)"
                label={{
                  value: '€/MWh',
                  angle: 90,
                  position: 'insideRight',
                  style: { fontSize: 10, fill: 'var(--muted-foreground)' },
                }}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  background: 'var(--popover)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  boxShadow: '0 4px 12px rgba(20, 14, 6, 0.08)',
                }}
                labelFormatter={(label) => `Day: ${label}`}
                formatter={(value, name) => [
                  fmtNumber(Number(value), 1),
                  String(name),
                ]}
              />
              <Area
                yAxisId="energy"
                type="monotone"
                dataKey="solar_mwh"
                name="Solar (MWh/day)"
                stroke={SOLAR_COLOR}
                fill="url(#bold-solar)"
                strokeWidth={1.4}
              />
              <Area
                yAxisId="energy"
                type="monotone"
                dataKey="load_mwh"
                name="Load (MWh/day)"
                stroke={LOAD_COLOR}
                fill="url(#bold-load)"
                strokeWidth={1.4}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="market_price_eur_mwh"
                name="Spot price (€/MWh)"
                stroke={PRICE_COLOR}
                strokeWidth={1.8}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </TabsContent>

      <TabsContent value="week" className="pt-4">
        <div className="aspect-[16/6] w-full min-h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={week}
              margin={{ top: 10, right: 28, left: 0, bottom: 4 }}
            >
              <defs>
                <linearGradient id="bold-solar-week" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={SOLAR_COLOR} stopOpacity={0.55} />
                  <stop offset="100%" stopColor={SOLAR_COLOR} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
              <XAxis
                dataKey="hour"
                tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                tickFormatter={(h: number) => `${Math.floor(h / 24)}d`}
                minTickGap={20}
                stroke="var(--border)"
              />
              <YAxis
                yAxisId="energy"
                tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                width={50}
                tickFormatter={(v: number) => fmtNumber(v, 0)}
                stroke="var(--border)"
                label={{
                  value: 'MW',
                  angle: -90,
                  position: 'insideLeft',
                  style: { fontSize: 10, fill: 'var(--muted-foreground)' },
                }}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                width={50}
                tickFormatter={(v: number) => `€${fmtNumber(v, 0)}`}
                stroke="var(--border)"
                label={{
                  value: '€/MWh',
                  angle: 90,
                  position: 'insideRight',
                  style: { fontSize: 10, fill: 'var(--muted-foreground)' },
                }}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  background: 'var(--popover)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  boxShadow: '0 4px 12px rgba(20, 14, 6, 0.08)',
                }}
                labelFormatter={(_, payload) =>
                  payload?.[0]?.payload?.timestamp ?? ''
                }
                formatter={(value, name) => [
                  fmtNumber(Number(value), 2),
                  String(name),
                ]}
              />
              <Area
                yAxisId="energy"
                type="monotone"
                dataKey="solar_mwh"
                name="Solar (MW)"
                stroke={SOLAR_COLOR}
                fill="url(#bold-solar-week)"
                strokeWidth={1.4}
              />
              <Line
                yAxisId="energy"
                type="monotone"
                dataKey="load_mwh"
                name="Load (MW)"
                stroke={LOAD_COLOR}
                strokeWidth={1.4}
                dot={false}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="market_price_eur_mwh"
                name="Spot price (€/MWh)"
                stroke={PRICE_COLOR}
                strokeWidth={1.8}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </TabsContent>

      <TabsContent value="capture" className="pt-4">
        {capture.status === 'loading' && (
          <PanelLoading message="Computing annual capture rates…" />
        )}
        {capture.status === 'error' && <PanelError message={capture.message} />}
        {capture.status === 'success' && (
          <CaptureTimelineChart data={capture.data} />
        )}
      </TabsContent>
    </Tabs>
  )
}

function CaptureTimelineChart({ data }: { data: CaptureTimeline }) {
  const rows = data.years.map((year, i) => ({
    year,
    capture: data.capture_rate[i],
  }))
  return (
    <div>
      <p className="mb-2 text-[11px] text-muted-foreground">
        Production-weighted price ÷ baseload average per calendar year
        (central scenario). Horizon capture rate:{' '}
        <span className="font-mono font-semibold text-foreground">
          {(data.horizon_capture_rate * 100).toFixed(1)}%
        </span>
        . The decline is the cannibalisation ramp doing its work.
      </p>
      <div className="aspect-[16/6] w-full min-h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={rows}
            margin={{ top: 10, right: 28, left: 0, bottom: 4 }}
          >
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
            <XAxis
              dataKey="year"
              tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
              stroke="var(--border)"
            />
            <YAxis
              domain={[
                (min: number) => Math.floor((min - 0.03) * 20) / 20,
                (max: number) => Math.ceil((max + 0.03) * 20) / 20,
              ]}
              tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
              width={50}
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
              stroke="var(--border)"
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                background: 'var(--popover)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                boxShadow: '0 4px 12px rgba(20, 14, 6, 0.08)',
              }}
              formatter={(value) => [
                `${(Number(value) * 100).toFixed(1)}%`,
                'Capture rate',
              ]}
            />
            <Line
              type="monotone"
              dataKey="capture"
              name="Capture rate"
              stroke={SOLAR_COLOR}
              strokeWidth={2}
              dot={{ r: 3, fill: SOLAR_COLOR }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
