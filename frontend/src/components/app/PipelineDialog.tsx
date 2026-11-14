// Dialog showing how healthy the ingestion pipeline is: cycles, latency, throughput, feeds and extraction.
import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Observability } from '@/lib/api'
import { barHeights, formatDuration, minutesAgo, percent, STALE_AFTER_MINUTES } from '@/lib/insights'
import { cn } from '@/lib/utils'

/** Window choices offered in the dialog. */
const WINDOWS = [
  { hours: 24, label: '24 hours' },
  { hours: 168, label: '7 days' },
] as const

/** One headline figure. */
function Kpi({ label, value, note, warn }: { label: string; value: string; note?: string; warn?: boolean }) {
  return (
    <div className="rounded-lg border bg-background/50 px-3 py-2.5">
      <div className="text-[11px] tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className={cn('text-lg font-semibold tabular-nums', warn && 'text-negative')}>{value}</div>
      {note && <div className="text-[11.5px] text-muted-foreground">{note}</div>}
    </div>
  )
}

/** The pipeline-health dialog. */
export function PipelineDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [hours, setHours] = useState<number>(24)
  const [data, setData] = useState<Observability | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    let live = true
    api.observability(hours).then(
      (d) => live && (setData(d), setError('')),
      (e: Error) => live && setError(e.message),
    )
    return () => {
      live = false
    }
  }, [open, hours])

  const stale = data !== null && data.runs.minutes_since_ok !== null && data.runs.minutes_since_ok > STALE_AFTER_MINUTES
  const heights = barHeights(data?.throughput.series.map((s) => s.added) ?? [])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Activity className="size-4 text-link" aria-hidden /> Pipeline health
          </DialogTitle>
          <DialogDescription>How the shared feeds are being ingested: failures, speed, volume and how often the full article could be read.</DialogDescription>
        </DialogHeader>

        <div role="radiogroup" aria-label="Time window" className="flex gap-1">
          {WINDOWS.map((w) => (
            <Button key={w.hours} role="radio" aria-checked={hours === w.hours} size="sm" variant={hours === w.hours ? 'secondary' : 'ghost'} onClick={() => setHours(w.hours)}>
              {w.label}
            </Button>
          ))}
        </div>

        <ScrollArea className="max-h-[26rem] pr-3">
          {error && <p className="text-sm text-negative">Could not load pipeline health: {error}</p>}
          {!error && !data && <Skeleton className="h-48 w-full" />}
          {data && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Kpi
                  label="Last good run"
                  value={minutesAgo(data.runs.minutes_since_ok)}
                  note={stale ? 'Older than expected: check the scheduler' : `${data.runs.total} cycles in the window`}
                  warn={stale}
                />
                <Kpi label="Cycles succeeded" value={percent(data.runs.success_rate)} note={`${data.runs.failed} failed`} warn={data.runs.failed > 0} />
                <Kpi label="Cycle time" value={formatDuration(data.runs.p50_ms)} note={`p95 ${formatDuration(data.runs.p95_ms)}`} />
                <Kpi label="New articles" value={String(data.throughput.added)} note={`${data.throughput.per_hour} per hour`} />
                <Kpi label="Full page read" value={percent(data.extraction.success_rate)} note={`${data.extraction.page} read, ${data.extraction.fallback} used the excerpt`} />
                <Kpi
                  label="Waiting"
                  value={String(data.backlog.awaiting_enrichment)}
                  note={data.backlog.awaiting_embedding === null ? 'for a full summary' : `for a summary, ${data.backlog.awaiting_embedding} for embedding`}
                />
              </div>

              {data.throughput.series.length > 0 && (
                <div>
                  <h3 className="mb-1.5 text-xs font-semibold">New articles over time</h3>
                  <ol className="flex h-16 items-end gap-0.5" aria-label="New articles per period">
                    {data.throughput.series.map((s, i) => (
                      <li key={s.at} className="flex h-full flex-1 items-end" title={`${s.at.replace('T', ' ')}: ${s.added} new`}>
                        <div className="w-full rounded-t-sm bg-link/70" style={{ height: `${heights[i]}%`, minHeight: s.added ? 2 : 0 }} />
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              <div>
                <h3 className="mb-1.5 flex items-center gap-2 text-xs font-semibold">
                  Feeds
                  <Badge variant="outline" className="font-normal">{data.feeds.ok} healthy</Badge>
                  {data.feeds.failing > 0 && <Badge variant="outline" className="font-normal text-negative">{data.feeds.failing} with failures</Badge>}
                </h3>
                {data.feeds.items.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No feed activity recorded in this window yet.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {data.feeds.items.map((f) => (
                      <li key={f.feed} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 rounded-lg border bg-background/50 px-3 py-2 text-xs">
                        <span className="min-w-0 font-medium">{f.feed}</span>
                        <span className="flex flex-wrap items-center gap-x-3 text-muted-foreground tabular-nums">
                          <span className={cn(f.failures > 0 && 'font-medium text-negative')}>{f.failures}/{f.runs} failed</span>
                          <span>p95 {formatDuration(f.p95_latency_ms)}</span>
                          <span>{f.articles_added} new</span>
                        </span>
                        {f.last_error && <span className="basis-full truncate text-[11px] text-negative" title={f.last_error}>Last error: {f.last_error}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
