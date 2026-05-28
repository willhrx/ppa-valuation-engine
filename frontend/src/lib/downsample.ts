// Client-side downsampling for the full-horizon hourly payload.
//
// The backend ships ~87,600 hourly points; recharts can render that, but it
// blocks the main thread and the chart is illegible anyway. We aggregate to
// daily means for the overview, and provide a windowed slice for the
// sample-week view.

import type { ProfilesResponse } from './api'

export interface DailyPoint {
  date: string  // YYYY-MM-DD
  solar_mwh: number
  market_price_eur_mwh: number
  load_mwh: number
}

export function aggregateToDaily(profiles: ProfilesResponse): DailyPoint[] {
  const buckets = new Map<
    string,
    { solar: number; price: number; load: number; n: number }
  >()

  for (let i = 0; i < profiles.timestamps.length; i++) {
    const day = profiles.timestamps[i].slice(0, 10)
    const entry = buckets.get(day) ?? { solar: 0, price: 0, load: 0, n: 0 }
    entry.solar += profiles.solar_mwh[i]
    entry.price += profiles.market_price_eur_mwh[i]
    entry.load += profiles.load_mwh[i]
    entry.n += 1
    buckets.set(day, entry)
  }

  return Array.from(buckets.entries()).map(([date, b]) => ({
    date,
    solar_mwh: b.solar,                       // daily total MWh
    market_price_eur_mwh: b.price / b.n,      // daily mean €/MWh
    load_mwh: b.load,                         // daily total MWh
  }))
}

export interface HourlyPoint {
  timestamp: string
  hour: number  // hours since slice start, for nicer x-axis ticks
  solar_mwh: number
  market_price_eur_mwh: number
  load_mwh: number
}

/**
 * Take a sample slice of N consecutive hours starting at the first timestamp
 * whose date matches `startDate` (YYYY-MM-DD). Falls back to the first N
 * hours if no match is found.
 */
export function sliceWindow(
  profiles: ProfilesResponse,
  startDate: string,
  hours: number,
): HourlyPoint[] {
  let startIdx = profiles.timestamps.findIndex((t) => t.startsWith(startDate))
  if (startIdx < 0) startIdx = 0
  const endIdx = Math.min(startIdx + hours, profiles.timestamps.length)

  const points: HourlyPoint[] = []
  for (let i = startIdx; i < endIdx; i++) {
    points.push({
      timestamp: profiles.timestamps[i],
      hour: i - startIdx,
      solar_mwh: profiles.solar_mwh[i],
      market_price_eur_mwh: profiles.market_price_eur_mwh[i],
      load_mwh: profiles.load_mwh[i],
    })
  }
  return points
}
