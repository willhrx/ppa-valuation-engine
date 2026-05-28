import { useMemo, useState } from 'react'

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { PanelError, PanelLoading } from '@/components/spinner'
import {
  api,
  type PPAConfig,
  type ValuationMatrixResponse,
  type ValuationRow,
} from '@/lib/api'
import { fmtEurMillion, fmtEurPerMwh, fmtGwh, fmtPercent } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAsyncCall } from '@/hooks/useAsync'

interface ValuationMatrixTableProps {
  config: PPAConfig | null
  baseStrike: number
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

const columnHelper = createColumnHelper<ValuationRow>()

export function ValuationMatrixTable({
  config,
  baseStrike,
}: ValuationMatrixTableProps) {
  const { state, refetch } = useAsyncCall<ValuationMatrixResponse>(
    (signal) => {
      if (!config) return Promise.reject(new Error('no config'))
      return api.valuationMatrix(config, baseStrike, signal)
    },
    [config, baseStrike],
  )

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-sm">Valuation matrix</CardTitle>
          <CardDescription className="text-xs">
            12 supply × pricing combinations at the central scenario, base
            strike <span className="font-mono">{baseStrike.toFixed(1)} €/MWh</span>.
          </CardDescription>
        </div>
        {state.status === 'success' && (
          <button
            type="button"
            className="text-[10px] text-muted-foreground underline-offset-2 hover:underline"
            onClick={refetch}
          >
            refresh
          </button>
        )}
      </CardHeader>
      <CardContent>
        {state.status === 'idle' && (
          <p className="text-xs text-muted-foreground">
            Apply a configuration to compute the matrix.
          </p>
        )}
        {state.status === 'loading' && (
          <PanelLoading message="Computing 12 valuations…" />
        )}
        {state.status === 'error' && <PanelError message={state.message} />}
        {state.status === 'success' && <Matrix rows={state.data.rows} />}
      </CardContent>
    </Card>
  )
}

function Matrix({ rows }: { rows: ValuationRow[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'producer_npv', desc: true },
  ])

  const columns = useMemo(
    () => [
      columnHelper.accessor('supply_structure', {
        header: 'Supply',
        cell: (info) => (
          <span className="font-medium">
            {SUPPLY_LABELS[info.getValue()] ?? info.getValue()}
          </span>
        ),
      }),
      columnHelper.accessor('pricing_structure', {
        header: 'Pricing',
        cell: (info) =>
          PRICING_LABELS[info.getValue()] ?? info.getValue(),
      }),
      columnHelper.accessor('producer_npv', {
        header: 'Producer NPV',
        cell: (info) => (
          <span
            className={cn(
              'font-mono tabular-nums',
              info.getValue() < 0 ? 'text-destructive' : '',
            )}
          >
            {fmtEurMillion(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('average_strike_eur_mwh', {
        header: 'Avg strike',
        cell: (info) => (
          <span className="font-mono tabular-nums">
            {fmtEurPerMwh(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('capture_rate', {
        header: 'Capture',
        cell: (info) => (
          <span className="font-mono tabular-nums">
            {fmtPercent(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('total_volume_mwh', {
        header: 'Volume',
        cell: (info) => (
          <span className="font-mono tabular-nums">
            {fmtGwh(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('volume_value', {
        header: 'Volume value',
        cell: (info) => (
          <span className="font-mono tabular-nums">
            {fmtEurMillion(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('profile_value', {
        header: 'Profile value',
        cell: (info) => (
          <span
            className={cn(
              'font-mono tabular-nums',
              info.getValue() < 0 ? 'text-destructive' : '',
            )}
          >
            {fmtEurMillion(info.getValue())}
          </span>
        ),
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

  return (
    <div className="max-h-[420px] overflow-auto rounded-md border">
      <Table className="text-xs">
        <TableHeader className="sticky top-0 bg-background">
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => {
                const sort = header.column.getIsSorted()
                return (
                  <TableHead
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="cursor-pointer select-none whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide"
                  >
                    <span className="inline-flex items-center gap-1">
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
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id} className="hover:bg-muted/40">
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id} className="whitespace-nowrap py-1.5">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
