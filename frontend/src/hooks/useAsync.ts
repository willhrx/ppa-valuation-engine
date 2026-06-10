import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '@/lib/api'

export type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading'; startedAt: number }
  | { status: 'success'; data: T }
  | { status: 'error'; message: string }

/** Shape returned by useAsyncCall — passable down to sharing components. */
export interface AsyncCallHandle<T> {
  state: AsyncState<T>
  refetch: () => void
}

/**
 * Fires `fn(signal)` whenever any entry in `deps` changes (after the first
 * truthy entry — set deps to `[null]` to suppress until ready).
 *
 * Aborts the in-flight request when deps change so the panel never holds a
 * stale response.
 */
export function useAsyncCall<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  deps: ReadonlyArray<unknown>,
): AsyncCallHandle<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: 'idle' })
  const fnRef = useRef(fn)
  fnRef.current = fn

  const tick = useRef(0)

  const run = useCallback(() => {
    const controller = new AbortController()
    const myTick = ++tick.current
    setState({ status: 'loading', startedAt: Date.now() })
    fnRef.current(controller.signal).then(
      (data) => {
        if (myTick === tick.current) setState({ status: 'success', data })
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
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (deps.some((d) => d === null)) {
      setState({ status: 'idle' })
      return
    }
    return run()
    // deps are user-controlled — we want them tracked verbatim
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { state, refetch: run }
}
