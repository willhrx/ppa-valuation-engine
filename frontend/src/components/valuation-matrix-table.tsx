import { Fragment, useMemo, useState } from 'react'

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'

import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { PanelError, PanelLoading } from '@/components/spinner'
import { RiskRowDetail } from '@/components/risk-row-detail'
import {
  api,
  type ComboRiskSummary,
  type PPAConfig,
  type ValuationMatrixResponse,
  type ValuationRow,
} from '@/lib/api'
import { fmtEurMillion, fmtEurPerMwh, fmtGwh, fmtPercent } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAsyncCall } from '@/hooks/useAsync'
import type { RiskSimulationHandle } from '@/hooks/useRiskSimulation'

interface ValuationMatrixTableProps {
  config: PPAConfig | null
  baseStrike: number
  simulation: RiskSimulationHandle
}

const SUPPLY_LABELS: Record<string, string> = {
  PayAsProduced: 'Pay-as-produced',
  PayAsNominated: 'Pay-as-nominated',
  Baseload: 'Baseload',
}

const PRICING_LABELS: Record<string, string> = {
  FixedFlat: 'Fixed flat',
  FixedEscalated: 'Fixed escalated',
  IndexedWithFloorCap: 'Indexed + floor/cap',
  Floating: 'Floating',
}

const SUPPLY_COLOR: Record<string, string> = {
  PayAsProduced: 'var(--solar)',
  PayAsNominated: 'var(--load)',
  Baseload: 'var(--price)',
}

const SUPPLY_LETTER: Record<string, string> = {
  PayAsProduced: 'P',
  PayAsNominated: 'N',
  Baseload: 'B',
}

const columnHelper = createColumnHelper<ValuationRow>()

const comboKey = (supply: string, pricing: string) => `${supply}::${pricing}`

export function ValuationMatrixTable({
  config,
  baseStrike,
  simulation,
}: ValuationMatrixTableProps) {
  const { state, refetch } = useAsyncCall<ValuationMatrixResponse>(
    (signal) => {
      if (!config) return Promise.reject(new Error('no config'))
      return api.valuationMatrix(config, baseStrike, signal)
    },
    [config, baseStrike],
  )

  return (
    <Card className="p-0">
      <div className="flex items-start justify-between gap-4 border-b px-6 pt-5 pb-4">
        <div>
          <div className="text-sm font-semibold tracking-[-0.005em]">
            Valuation &amp; risk matrix
          </div>
          <p className="mt-1 text-[11.5px] text-muted-foreground">
            12 supply × pricing combinations · base strike{' '}
            <span className="font-mono font-semibold text-foreground">
              €{baseStrike.toFixed(1)}/MWh
            </span>{' '}
            · expand a row for its Monte Carlo risk distribution
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RunRiskButton simulation={simulation} disabled={!config} />
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
      </div>
      <CardContent className="p-0">
        {state.status === 'idle' && (
          <p className="px-6 py-4 text-xs text-muted-foreground">
            Apply a configuration to compute the matrix.
          </p>
        )}
        {state.status === 'loading' && (
          <PanelLoading message="Computing 12 valuations…" />
        )}
        {state.status === 'error' && <PanelError message={state.message} />}
        {state.status === 'success' && (
          <Matrix rows={state.data.rows} simulation={simulation} />
        )}
      </CardContent>
    </Card>
  )
}

function RunRiskButton({
  simulation,
  disabled,
}: {
  simulation: RiskSimulationHandle
  disabled: boolean
}) {
  const { state, run } = simulation
  if (state.status === 'loading') {
    const elapsed = Math.floor((Date.now() - state.startedAt) / 1000)
    return (
      <span
        className="inline-flex items-center gap-2 rounded-[7px] border px-3 py-1.5 font-mono text-[11px]"
        style={{
          background: 'var(--accent-soft)',
          borderColor:
            'color-mix(in oklch, var(--accent) 25%, transparent)',
          color: 'var(--accent-deep)',
        }}
      >
        <span
          className="h-1.5 w-1.5 animate-pulse rounded-full"
          style={{ background: 'var(--accent)' }}
        />
        Running risk analysis · {elapsed}s
      </span>
    )
  }
  if (state.status === 'success') {
    return (
      <span className="inline-flex items-center gap-3">
        <span
          className="inline-flex items-center gap-2 rounded-[7px] border px-3 py-1.5 font-mono text-[11px]"
          style={{
            background: 'var(--positive-soft)',
            borderColor:
              'color-mix(in oklch, var(--positive) 25%, transparent)',
            color: 'var(--positive)',
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: 'var(--positive)' }}
          />
          {state.data.n_paths} paths · {state.data.elapsed_seconds.toFixed(1)}s
        </span>
        <button
          type="button"
          className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
          onClick={run}
        >
          re-run
        </button>
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={run}
      disabled={disabled}
      className="rounded-[7px] border px-3 py-1.5 text-[11.5px] font-semibold tracking-[-0.005em] text-primary-foreground transition-shadow hover:shadow disabled:cursor-not-allowed disabled:opacity-50"
      style={{
        background:
          'linear-gradient(180deg, var(--accent), var(--accent-deep))',
        borderColor: 'var(--accent-deep)',
        boxShadow:
          'inset 0 1px 0 color-mix(in oklch, white 20%, transparent)',
      }}
    >
      Run risk analysis · ~45s
    </button>
  )
}

function SupplyChip({ supply }: { supply: string }) {
  const color = SUPPLY_COLOR[supply] ?? 'var(--muted-foreground)'
  const letter = SUPPLY_LETTER[supply] ?? '·'
  return (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded-[5px] text-[10px] font-bold text-white"
      style={{
        background: color,
        boxShadow: `0 1px 2px color-mix(in oklch, ${color} 30%, transparent)`,
      }}
    >
      {letter}
    </span>
  )
}

function Matrix({
  rows,
  simulation,
}: {
  rows: ValuationRow[]
  simulation: RiskSimulationHandle
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'producer_npv', desc: true },
  ])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const npvMax = useMemo(
    () => Math.max(1, ...rows.map((r) => Math.abs(r.producer_npv))),
    [rows],
  )

  const riskByKey = useMemo(() => {
    if (simulation.state.status !== 'success') return new Map<string, ComboRiskSummary>()
    const map = new Map<string, ComboRiskSummary>()
    for (const c of simulation.state.data.risk_summary.combinations) {
      map.set(comboKey(c.supply_structure, c.pricing_structure), c)
    }
    return map
  }, [simulation.state])

  const riskAvailable = simulation.state.status === 'success'

  const toggleRow = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const columns = useMemo(
    () => [
      columnHelper.accessor('supply_structure', {
        header: 'Supply',
        cell: (info) => (
          <span className="inline-flex items-center gap-2 font-medium">
            <SupplyChip supply={info.getValue()} />
            {SUPPLY_LABELS[info.getValue()] ?? info.getValue()}
          </span>
        ),
      }),
      columnHelper.accessor('pricing_structure', {
        header: 'Pricing',
        cell: (info) => (
          <span style={{ color: 'var(--text-soft)' }}>
            {PRICING_LABELS[info.getValue()] ?? info.getValue()}
          </span>
        ),
      }),
      columnHelper.accessor('producer_npv', {
        header: 'Producer NPV',
        cell: (info) => (
          <span
            className={cn(
              'font-mono font-semibold tabular-nums',
              info.getValue() < 0 && 'text-[color:var(--negative)]',
            )}
          >
            {fmtEurMillion(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('average_strike_eur_mwh', {
        header: 'Avg strike',
        cell: (info) => (
          <span
            className="font-mono tabular-nums"
            style={{ color: 'var(--text-soft)' }}
          >
            {fmtEurPerMwh(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('capture_rate', {
        header: 'Capture',
        cell: (info) => (
          <span
            className="font-mono tabular-nums"
            style={{ color: 'var(--text-soft)' }}
          >
            {fmtPercent(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('total_volume_mwh', {
        header: 'Volume',
        cell: (info) => (
          <span
            className="font-mono tabular-nums"
            style={{ color: 'var(--text-soft)' }}
          >
            {fmtGwh(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('profile_value', {
        header: 'Profile value',
        cell: (info) => {
          const v = info.getValue()
          const isNeg = v < 0
          return (
            <span
              className="inline-block rounded-md px-2 py-0.5 font-mono text-[11.5px] font-semibold tabular-nums"
              style={{
                background: isNeg
                  ? 'var(--negative-soft)'
                  : 'var(--positive-soft)',
                color: isNeg ? 'var(--negative)' : 'var(--positive)',
              }}
            >
              {fmtEurMillion(v)}
            </span>
          )
        },
      }),
    ],
    [],
  )

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const sorted = table.getRowModel().rows
  const bestId = sorted[0]?.id
  const worstId = sorted[sorted.length - 1]?.id
  const totalCols = columns.length + 2 // chevron + rank

  return (
    <div className="max-h-[640px] overflow-auto">
      <Table className="text-xs">
        <TableHeader className="sticky top-0 z-10">
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id} className="border-b">
              <TableHead className="w-8 bg-[color:var(--surface-alt)] px-2 py-2.5" />
              {group.headers.map((header, idx) => {
                const sort = header.column.getIsSorted()
                const numeric = idx >= 2
                return (
                  <TableHead
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className={cn(
                      'cursor-pointer bg-[color:var(--surface-alt)] px-4 py-2.5 text-[10px] font-bold tracking-[0.08em] uppercase text-muted-foreground select-none',
                      numeric && 'text-right',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-flex items-center gap-1',
                        numeric && 'justify-end',
                      )}
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                      {sort === 'asc' && '↑'}
                      {sort === 'desc' && '↓'}
                    </span>
                  </TableHead>
                )
              })}
              <TableHead className="bg-[color:var(--surface-alt)] px-4 py-2.5 text-right text-[10px] font-bold tracking-[0.08em] uppercase text-muted-foreground">
                Rank
              </TableHead>
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {sorted.map((row) => {
            const isBest = row.id === bestId
            const isWorst = row.id === worstId
            const pct = Math.max(
              0,
              Math.min(1, row.original.producer_npv / npvMax),
            )
            const key = comboKey(
              row.original.supply_structure,
              row.original.pricing_structure,
            )
            const isOpen = expanded.has(key)
            const combo = riskByKey.get(key)
            return (
              <Fragment key={key}>
                <TableRow
                  className={cn(
                    'border-b hover:bg-[color:var(--accent-soft)]/40',
                    riskAvailable && 'cursor-pointer',
                  )}
                  onClick={() => {
                    if (riskAvailable) toggleRow(key)
                  }}
                  style={
                    isBest
                      ? {
                          background:
                            'linear-gradient(90deg, color-mix(in oklch, var(--accent-soft) 80%, transparent), transparent 60%)',
                        }
                      : undefined
                  }
                >
                  <TableCell className="w-8 px-2 py-3 text-center">
                    {riskAvailable ? (
                      <span
                        className="inline-block text-[10px] text-muted-foreground transition-transform"
                        style={{
                          transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                        }}
                        aria-label={isOpen ? 'Collapse' : 'Expand'}
                      >
                        ▶
                      </span>
                    ) : (
                      <span
                        className="text-[10px] text-muted-foreground/40"
                        title="Run risk analysis to see distributions"
                      >
                        ·
                      </span>
                    )}
                  </TableCell>
                  {row.getVisibleCells().map((cell, idx) => {
                    const numeric = idx >= 2
                    return (
                      <TableCell
                        key={cell.id}
                        className={cn(
                          'whitespace-nowrap px-4 py-3',
                          numeric && 'text-right',
                        )}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    )
                  })}
                  <TableCell className="px-4 py-3" style={{ width: 180 }}>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[color:var(--surface-alt)]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pct * 100}%`,
                            background: isBest
                              ? 'linear-gradient(90deg, var(--accent), var(--solar-deep))'
                              : isWorst
                                ? 'var(--negative)'
                                : 'var(--text-soft)',
                          }}
                        />
                      </div>
                      {isBest && (
                        <span
                          className="rounded-[4px] px-1.5 py-0.5 text-[10px] font-bold tracking-[0.04em] text-white"
                          style={{ background: 'var(--accent)' }}
                        >
                          BEST
                        </span>
                      )}
                      {isWorst && (
                        <span
                          className="rounded-[4px] px-1.5 py-0.5 text-[10px] font-bold tracking-[0.04em]"
                          style={{
                            background: 'var(--negative-soft)',
                            color: 'var(--negative)',
                          }}
                        >
                          WORST
                        </span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
                {isOpen && combo && (
                  <TableRow className="border-b">
                    <TableCell colSpan={totalCols} className="p-0">
                      <RiskRowDetail combo={combo} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
