import { useEffect, useState } from 'react'

import { ConfigPanel } from '@/components/config-panel'
import { KpiStrip } from '@/components/kpi-strip'
import { ProfilesCharts } from '@/components/profiles-charts'
import { SolverPanel } from '@/components/solver-panel'
import { ValuationMatrixTable } from '@/components/valuation-matrix-table'
import { PanelError, PanelLoading } from '@/components/spinner'
import { useAsyncCall } from '@/hooks/useAsync'
import { useRiskSimulation } from '@/hooks/useRiskSimulation'
import {
  api,
  ApiError,
  type PPAConfig,
  type ValuationMatrixResponse,
} from '@/lib/api'

const DEFAULT_BASE_STRIKE = 65.0

type DefaultsState =
  | { status: 'loading' }
  | { status: 'ready'; config: PPAConfig }
  | { status: 'error'; message: string }

interface NavItem {
  label: string
  anchor: string
}

const NAV: NavItem[] = [
  { label: 'Deal setup', anchor: '#deal-setup' },
  { label: 'Profiles', anchor: '#profiles' },
  { label: 'Valuation', anchor: '#valuation' },
  { label: 'Risk', anchor: '#valuation' },
  { label: 'Solver', anchor: '#solver' },
]

function App() {
  const [defaults, setDefaults] = useState<DefaultsState>({ status: 'loading' })
  const [applied, setApplied] = useState<{
    config: PPAConfig
    baseStrike: number
  } | null>(null)
  const [activeAnchor, setActiveAnchor] = useState<string>('#deal-setup')
  const [nPaths, setNPaths] = useState<number>(500)

  const simulation = useRiskSimulation(
    applied?.config ?? null,
    applied?.baseStrike ?? DEFAULT_BASE_STRIKE,
    nPaths,
  )

  // Single shared valuation-matrix fetch — the KPI strip and the matrix
  // table previously fired identical POSTs side by side.
  const matrix = useAsyncCall<ValuationMatrixResponse>(
    (signal) => {
      if (!applied) return Promise.reject(new Error('no config'))
      return api.valuationMatrix(applied.config, applied.baseStrike, signal)
    },
    [applied ?? null],
  )

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

  useEffect(() => {
    const targets = ['deal-setup', 'profiles', 'valuation', 'solver']
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null)
    if (targets.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActiveAnchor(`#${visible.target.id}`)
      },
      { rootMargin: '-80px 0px -50% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] },
    )
    for (const t of targets) observer.observe(t)
    return () => observer.disconnect()
  }, [defaults.status])

  const handleReset = async () => {
    const fresh = await api.configDefaults()
    setApplied({ config: fresh, baseStrike: DEFAULT_BASE_STRIKE })
    return fresh
  }

  const runRisk = () => simulation.run()
  const riskRunning = simulation.state.status === 'loading'
  const riskFailed = simulation.state.status === 'error'
  const riskStale =
    simulation.state.status === 'success' && simulation.state.stale
  const headerButtonLabel = riskRunning
    ? 'Running…'
    : riskFailed
      ? 'Simulation failed — retry'
      : riskStale
        ? 'Re-run simulation →'
        : `Run ${nPaths}-path simulation →`

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b bg-card/95 backdrop-blur">
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
            {NAV.map(({ label, anchor }) => {
              const active = anchor === activeAnchor
              return (
                <a
                  key={label}
                  href={anchor}
                  className="rounded-[7px] border px-3 py-1.5 text-xs transition-colors"
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
                  {label}
                </a>
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
            onClick={runRisk}
            disabled={!applied || riskRunning}
            title={
              riskFailed && simulation.state.status === 'error'
                ? simulation.state.message
                : undefined
            }
            className="h-9 rounded-[9px] px-4 text-[12.5px] font-semibold tracking-[-0.005em] text-primary-foreground transition-shadow hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-60"
            style={{
              background: riskFailed
                ? 'linear-gradient(180deg, var(--negative), color-mix(in oklch, var(--negative) 80%, black))'
                : 'linear-gradient(180deg, var(--accent), var(--accent-deep))',
              boxShadow:
                'inset 0 1px 0 var(--accent-deep), 0 4px 12px color-mix(in oklch, var(--accent) 25%, transparent)',
            }}
          >
            {headerButtonLabel}
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
            <KpiStrip matrix={matrix} />

            <div className="grid grid-cols-12 gap-4">
              <aside
                id="deal-setup"
                className="col-span-12 scroll-mt-20 lg:col-span-3"
              >
                <div className="lg:sticky lg:top-20 lg:flex lg:h-[calc(100vh-6rem)] lg:flex-col">
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
                <div id="profiles" className="scroll-mt-20">
                  <ProfilesCharts config={applied.config} />
                </div>
                <div id="valuation" className="scroll-mt-20">
                  <ValuationMatrixTable
                    matrix={matrix}
                    hasConfig={applied !== null}
                    baseStrike={applied.baseStrike}
                    simulation={simulation}
                    nPaths={nPaths}
                    onNPathsChange={setNPaths}
                  />
                </div>
                <div id="solver" className="scroll-mt-20">
                  <SolverPanel
                    config={applied.config}
                    baseStrike={applied.baseStrike}
                  />
                </div>
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
