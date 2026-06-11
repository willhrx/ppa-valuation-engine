import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '@/lib/api'

export type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; message: string }

/** Shape returned by useAsyncCall — passable down to sharing components. */
export interface AsyncCallHandle<T> {
  state: AsyncState<T>
  refetch: () => void
}

type SettledResult<T> =
  | { status: 'success'; data: T }
  | { status: 'error'; message: string }

function sameKey(a: ReadonlyArray<unknown>, b: ReadonlyArray<unknown>) {
  return a.length === b.length && a.every((v, i) => Object.is(v, b[i]))
}

/**
 * Fires `fn(signal)` whenever any entry in `deps` changes (after the first
 * truthy entry — set deps to `[null]` to suppress until ready).
 *
 * Aborts the in-flight request when deps change so the panel never holds a
 * stale response.
 *
 * Only settled results are stored, tagged with the deps key that produced
 * them; `loading` is derived as "the current key has no settled result yet".
 * This keeps every setState inside async callbacks, so the effect never
 * triggers a cascading synchronous render.
 */
export function useAsyncCall<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  deps: ReadonlyArray<unknown>,
): AsyncCallHandle<T> {
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })

  const [refetchCount, setRefetchCount] = useState(0)
  const [settled, setSettled] = useState<{
    key: ReadonlyArray<unknown>
    result: SettledResult<T>
  } | null>(null)

  const tick = useRef(0)

  const suppressed = deps.some((d) => d === null)
  const key = [...deps, refetchCount]

  useEffect(() => {
    if (suppressed) return
    const controller = new AbortController()
    const myTick = ++tick.current
    fnRef.current(controller.signal).then(
      (data) => {
        if (myTick === tick.current)
          setSettled({ key, result: { status: 'success', data } })
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
        setSettled({ key, result: { status: 'error', message } })
      },
    )
    return () => controller.abort()
    // deps are user-controlled — we want them tracked verbatim
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refetchCount])

  const refetch = useCallback(() => setRefetchCount((c) => c + 1), [])

  const state: AsyncState<T> = suppressed
    ? { status: 'idle' }
    : settled !== null && sameKey(settled.key, key)
      ? settled.result
      : { status: 'loading' }

  return { state, refetch }
}
