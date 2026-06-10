import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, api, type MonteCarloResponse, type PPAConfig } from '@/lib/api'

export type RiskSimState =
  | { status: 'idle' }
  | { status: 'loading'; startedAt: number }
  | { status: 'success'; data: MonteCarloResponse; stale: boolean }
  | { status: 'error'; message: string }

export interface RiskSimulationHandle {
  state: RiskSimState
  run: () => void
  reset: () => void
}

export function useRiskSimulation(
  config: PPAConfig | null,
  baseStrike: number,
  nPaths: number = 500,
): RiskSimulationHandle {
  const [state, setState] = useState<RiskSimState>({ status: 'idle' })
  const controllerRef = useRef<AbortController | null>(null)
  const tick = useRef(0)

  const reset = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setState({ status: 'idle' })
  }, [])

  const configKey = config ? JSON.stringify(config) : null
  const baseStrikeKey = baseStrike

  // On config / strike change: abort an in-flight run, but keep completed
  // results viewable — just mark them stale so the UI can prompt a re-run.
  useEffect(() => {
    setState((prev) => {
      if (prev.status === 'loading') {
        controllerRef.current?.abort()
        controllerRef.current = null
        return { status: 'idle' }
      }
      if (prev.status === 'success' && !prev.stale) {
        return { ...prev, stale: true }
      }
      if (prev.status === 'error') {
        return { status: 'idle' }
      }
      return prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configKey, baseStrikeKey])

  const run = useCallback(() => {
    if (!config) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const myTick = ++tick.current
    setState({ status: 'loading', startedAt: Date.now() })
    api.simulate(config, baseStrike, nPaths, controller.signal).then(
      (data) => {
        if (myTick === tick.current)
          setState({ status: 'success', data, stale: false })
      },
      (err: unknown) => {
        if (controller.signal.aborted) return
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
  }, [config, baseStrike, nPaths])

  return { state, run, reset }
}
