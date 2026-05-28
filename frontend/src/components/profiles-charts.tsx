import { useMemo } from 'react'

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PanelError, PanelLoading } from '@/components/spinner'
import { api, type PPAConfig, type ProfilesResponse } from '@/lib/api'
import { aggregateToDaily, sliceWindow } from '@/lib/downsample'
import { fmtNumber } from '@/lib/format'
import { useAsyncCall } from '@/hooks/useAsync'

interface ProfilesChartsProps {
  config: PPAConfig | null
}

const SOLAR_COLOR = 'var(--chart-1)'
const PRICE_COLOR = 'var(--chart-3)'
const LOAD_COLOR = 'var(--chart-2)'

export function ProfilesCharts({ config }: ProfilesChartsProps) {
  const { state, refetch } = useAsyncCall<ProfilesResponse>(
    (signal) => {
      if (!config) return Promise.reject(new Error('no config'))
      return api.profiles(config, signal)
    },
    [config],
  )

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-sm">Generation, load &amp; price profiles</CardTitle>
          <CardDescription className="text-xs">
            Central-scenario hourly series from{' '}
            <code>/api/profiles</code>, aggregated client-side.
          </CardDescription>
        </div>
        {state.status === 'success' && (
          <div className="text-right text-[10px] text-muted-foreground">
            {state.data.n_hours.toLocaleString()} hourly points ·{' '}
            {state.data.timezone}
            <button
              type="button"
              className="ml-2 underline-offset-2 hover:underline"
              onClick={refetch}
            >
              refresh
            </button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {state.status === 'idle' && (
          <p className="text-xs text-muted-foreground">
            Apply a configuration to load profiles.
          </p>
        )}
        {state.status === 'loading' && (
          <PanelLoading message="Generating 10-year hourly profile (~10–12 s)…" />
        )}
        {state.status === 'error' && <PanelError message={state.message} />}
        {state.status === 'success' && <ChartTabs profiles={state.data} />}
      </CardContent>
    </Card>
  )
}

function ChartTabs({ profiles }: { profiles: ProfilesResponse }) {
  const daily = useMemo(() => aggregateToDaily(profiles), [profiles])
  const week = useMemo(() => {
    // First full week of July, 2nd year of the horizon — guaranteed to land in summer.
    const year = Number(profiles.timestamps[0].slice(0, 4)) + 1
    return sliceWindow(profiles, `${year}-07-07`, 168)
  }, [profiles])

  return (
    <Tabs defaultValue="overview" className="w-full">
      <TabsList className="grid w-full max-w-md grid-cols-2">
        <TabsTrigger value="overview" className="text-xs">
          Horizon overview (daily)
        </TabsTrigger>
        <TabsTrigger value="week" className="text-xs">
          Sample week (hourly)
        </TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="pt-3">
        <div className="h-[360px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={daily}
              margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
            >
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d: string) => d.slice(0, 7)}
                minTickGap={40}
              />
              <YAxis
                yAxisId="energy"
                tick={{ fontSize: 10 }}
                width={50}
                tickFormatter={(v: number) => fmtNumber(v, 0)}
                label={{
                  value: 'MWh/day',
                  angle: -90,
                  position: 'insideLeft',
                  style: {
                    fontSize: 10,
                    fill: 'var(--muted-foreground)',
                  },
                }}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                tick={{ fontSize: 10 }}
                width={50}
                tickFormatter={(v: number) => fmtNumber(v, 0)}
                label={{
                  value: '€/MWh',
                  angle: 90,
                  position: 'insideRight',
                  style: {
                    fontSize: 10,
                    fill: 'var(--muted-foreground)',
                  },
                }}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  background: 'var(--popover)',
                  border: '1px solid var(--border)',
                }}
                labelFormatter={(label) => `Day: ${label}`}
                formatter={(value, name) => [
                  fmtNumber(Number(value), 1),
                  String(name),
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area
                yAxisId="energy"
                type="monotone"
                dataKey="solar_mwh"
                name="Solar (MWh/day)"
                stroke={SOLAR_COLOR}
                fill={SOLAR_COLOR}
                fillOpacity={0.25}
                strokeWidth={1}
              />
              <Area
                yAxisId="energy"
                type="monotone"
                dataKey="load_mwh"
                name="Load (MWh/day)"
                stroke={LOAD_COLOR}
                fill={LOAD_COLOR}
                fillOpacity={0.15}
                strokeWidth={1}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="market_price_eur_mwh"
                name="Spot price (€/MWh, daily mean)"
                stroke={PRICE_COLOR}
                strokeWidth={1.25}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </TabsContent>

      <TabsContent value="week" className="pt-3">
        <div className="h-[360px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={week}
              margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
            >
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="hour"
                tick={{ fontSize: 10 }}
                tickFormatter={(h: number) => `${Math.floor(h / 24)}d`}
                minTickGap={20}
              />
              <YAxis
                yAxisId="energy"
                tick={{ fontSize: 10 }}
                width={50}
                tickFormatter={(v: number) => fmtNumber(v, 0)}
                label={{
                  value: 'MWh/h',
                  angle: -90,
                  position: 'insideLeft',
                  style: {
                    fontSize: 10,
                    fill: 'var(--muted-foreground)',
                  },
                }}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                tick={{ fontSize: 10 }}
                width={50}
                tickFormatter={(v: number) => fmtNumber(v, 0)}
                label={{
                  value: '€/MWh',
                  angle: 90,
                  position: 'insideRight',
                  style: {
                    fontSize: 10,
                    fill: 'var(--muted-foreground)',
                  },
                }}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  background: 'var(--popover)',
                  border: '1px solid var(--border)',
                }}
                labelFormatter={(_, payload) =>
                  payload?.[0]?.payload?.timestamp ?? ''
                }
                formatter={(value, name) => [
                  fmtNumber(Number(value), 2),
                  String(name),
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area
                yAxisId="energy"
                type="monotone"
                dataKey="solar_mwh"
                name="Solar (MWh/h)"
                stroke={SOLAR_COLOR}
                fill={SOLAR_COLOR}
                fillOpacity={0.3}
                strokeWidth={1}
              />
              <Line
                yAxisId="energy"
                type="monotone"
                dataKey="load_mwh"
                name="Load (MWh/h)"
                stroke={LOAD_COLOR}
                strokeWidth={1}
                dot={false}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="market_price_eur_mwh"
                name="Spot price (€/MWh)"
                stroke={PRICE_COLOR}
                strokeWidth={1.25}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </TabsContent>
    </Tabs>
  )
}
