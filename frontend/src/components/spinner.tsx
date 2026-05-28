import { cn } from '@/lib/utils'

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent',
        className,
      )}
      role="status"
      aria-label="loading"
    />
  )
}

export function PanelLoading({ message }: { message?: string }) {
  return (
    <div className="flex h-full min-h-[200px] items-center justify-center gap-2 text-muted-foreground">
      <Spinner />
      <span className="text-sm">{message ?? 'Loading…'}</span>
    </div>
  )
}

export function PanelError({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-[120px] items-center justify-center px-4">
      <div className="max-w-md rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
        {message}
      </div>
    </div>
  )
}
