import { useEffect, useState } from 'react'

import { ConfigPanel } from '@/components/config-panel'
import { KpiStrip } from '@/components/kpi-strip'
import { ProfilesCharts } from '@/components/profiles-charts'
import { ValuationMatrixTable } from '@/components/valuation-matrix-table'
import { PanelError, PanelLoading } from '@/components/spinner'
import { api, ApiError, type PPAConfig } from '@/lib/api'

const DEFAULT_BASE_STRIKE = 65.0

type DefaultsState =
  | { status: 'loading' }
  | { status: 'ready'; config: PPAConfig }
  | { status: 'error'; message: string }

const NAV = ['Deal setup', 'Profiles', 'Valuation', 'Risk', 'Reports']

function App() {
  const [defaults, setDefaults] = useState<DefaultsState>({ status: 'loading' })
  const [applied, setApplied] = useState<{
    config: PPAConfig
    baseStrike: number
  } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api.configDefaults(controller.signal).then(
      (config) => {
        setDefaults({ status: 'ready', config })
        setApplied({ config, baseStrike: DEFAULT_BASE_STRIKE })
      },
      (err: unknown) => {
        if (controller.signal.aborted) return
        const message =
          err instanceof ApiError
            ? `${err.status}: ${String(err.detail ?? err.message)}`
            : err instanceof Error
              ? err.message
              : 'Unknown error'
        setDefaults({ status: 'error', message })
      },
    )
    return () => controller.abort()
  }, [])

  const handleReset = async () => {
    const fresh = await api.configDefaults()
    setApplied({ config: fresh, baseStrike: DEFAULT_BASE_STRIKE })
    return fresh
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-6 px-6">
          <div className="flex items-center gap-3">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-[9px]"
              style={{
                background:
                  'linear-gradient(135deg, var(--accent), var(--solar-deep))',
                boxShadow:
                  '0 4px 12px color-mix(in oklch, var(--accent) 25%, transparent)',
              }}
            >
              <SunIcon />
            </div>
            <div className="flex flex-col gap-px">
              <span className="text-sm font-semibold tracking-[-0.01em]">
                PPA Valuation Engine
              </span>
              <span className="text-[11px] text-muted-foreground">
                Dutch solar · scenario-conditional valuation
              </span>
            </div>
          </div>

          <nav className="ml-6 flex gap-1">
            {NAV.map((n, i) => {
              const active = i === 2
              return (
                <span
                  key={n}
                  className="rounded-[7px] border px-3 py-1.5 text-xs"
                  style={{
                    color: active
                      ? 'var(--foreground)'
                      : 'var(--muted-foreground)',
                    fontWeight: active ? 600 : 500,
                    background: active
                      ? 'var(--surface-alt)'
                      : 'transparent',
                    borderColor: active ? 'var(--border)' : 'transparent',
                  }}
                >
                  {n}
                </span>
              )
            })}
          </nav>

          <div className="flex-1" />

          {applied && (
            <div
              className="flex items-center gap-2.5 rounded-full border px-3 py-1.5 font-mono text-[11px]"
              style={{
                background: 'var(--accent-soft)',
                borderColor:
                  'color-mix(in oklch, var(--accent) 20%, transparent)',
                color: 'var(--accent-deep)',
              }}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{
                  background: 'var(--accent)',
                  boxShadow:
                    '0 0 0 3px color-mix(in oklch, var(--accent) 20%, transparent)',
                }}
              />
              <span>
                {applied.config.deal.start_date} → {applied.config.deal.end_date}
              </span>
              <span className="opacity-40">·</span>
              <span>{applied.config.solar.capacity_mw} MW solar</span>
              <span className="opacity-40">·</span>
              <span>
                disc {(applied.config.deal.discount_rate * 100).toFixed(1)}%
              </span>
            </div>
          )}

          <button
            type="button"
            className="h-9 rounded-[9px] px-4 text-[12.5px] font-semibold tracking-[-0.005em] text-primary-foreground transition-shadow hover:shadow-lg"
            style={{
              background:
                'linear-gradient(180deg, var(--accent), var(--accent-deep))',
              boxShadow:
                'inset 0 1px 0 var(--accent-deep), 0 4px 12px color-mix(in oklch, var(--accent) 25%, transparent)',
            }}
          >
            Run 500-path simulation →
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-5">
        {defaults.status === 'loading' && (
          <PanelLoading message="Loading defaults from /api/config/defaults …" />
        )}
        {defaults.status === 'error' && <PanelError message={defaults.message} />}
        {defaults.status === 'ready' && applied && (
          <div className="flex flex-col gap-4">
            <KpiStrip config={applied.config} baseStrike={applied.baseStrike} />

            <div className="grid grid-cols-12 gap-4">
              <aside className="col-span-12 lg:col-span-3">
                <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)]">
                  <ConfigPanel
                    initial={defaults.config}
                    baseStrike={DEFAULT_BASE_STRIKE}
                    onApply={(config, baseStrike) =>
                      setApplied({ config, baseStrike })
                    }
                    onReset={handleReset}
                  />
                </div>
              </aside>

              <section className="col-span-12 space-y-4 lg:col-span-9">
                <ProfilesCharts config={applied.config} />
                <ValuationMatrixTable
                  config={applied.config}
                  baseStrike={applied.baseStrike}
                />
              </section>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t bg-card">
        <div className="mx-auto flex h-11 max-w-[1600px] items-center justify-between px-6 font-mono text-[10.5px] text-muted-foreground">
          <span>FastAPI · Vite · React 19 · shadcn/ui</span>
          <span>
            <span>v0.4.2 ·</span>{' '}
            <a
              className="font-semibold hover:underline"
              style={{ color: 'var(--accent-deep)' }}
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
            >
              API docs ↗
            </a>
          </span>
        </div>
      </footer>
    </div>
  )
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 22 22" aria-hidden>
      <circle cx="11" cy="11" r="4.5" fill="#fff" />
      {Array.from({ length: 8 }).map((_, i) => {
        const a = (i / 8) * Math.PI * 2
        return (
          <line
            key={i}
            x1={11 + Math.cos(a) * 7.5}
            y1={11 + Math.sin(a) * 7.5}
            x2={11 + Math.cos(a) * 10}
            y2={11 + Math.sin(a) * 10}
            stroke="#fff"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        )
      })}
    </svg>
  )
}

export default App
