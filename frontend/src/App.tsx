import { useEffect, useState } from 'react'

import { ConfigPanel } from '@/components/config-panel'
import { ProfilesCharts } from '@/components/profiles-charts'
import { ValuationMatrixTable } from '@/components/valuation-matrix-table'
import { PanelError, PanelLoading } from '@/components/spinner'
import { api, ApiError, type PPAConfig } from '@/lib/api'

const DEFAULT_BASE_STRIKE = 65.0

type DefaultsState =
  | { status: 'loading' }
  | { status: 'ready'; config: PPAConfig }
  | { status: 'error'; message: string }

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
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between px-6">
          <div className="flex items-baseline gap-3">
            <span className="text-sm font-semibold tracking-tight">
              PPA Valuation Engine
            </span>
            <span className="text-xs text-muted-foreground">
              Dutch solar PPA · scenario-conditional valuation
            </span>
          </div>
          {applied && (
            <span className="font-mono text-xs text-muted-foreground">
              {applied.config.deal.start_date} →{' '}
              {applied.config.deal.end_date} · {applied.config.solar.capacity_mw}{' '}
              MW · disc{' '}
              {(applied.config.deal.discount_rate * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-4">
        {defaults.status === 'loading' && (
          <PanelLoading message="Loading defaults from /api/config/defaults …" />
        )}
        {defaults.status === 'error' && <PanelError message={defaults.message} />}
        {defaults.status === 'ready' && applied && (
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
        )}
      </main>

      <footer className="border-t">
        <div className="mx-auto flex h-10 max-w-[1600px] items-center justify-between px-6 text-[11px] text-muted-foreground">
          <span>FastAPI · Vite · React 19 · shadcn/ui</span>
          <a
            className="hover:underline"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            API docs ↗
          </a>
        </div>
      </footer>
    </div>
  )
}

export default App
