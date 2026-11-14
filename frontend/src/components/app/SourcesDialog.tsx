// Dialog listing each outlet's evidence-based source profile, with its working.
import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { toneBg, toneText } from '@/components/app/Sentiment'
import { api, type SourceList, type SourceProfile } from '@/lib/api'
import { percent, reliabilityTone } from '@/lib/insights'
import { cn } from '@/lib/utils'

/** The score as a coloured badge, or the "not enough data" label. */
export function ScoreBadge({ score, label }: { score: number | null; label: string }) {
  const tone = reliabilityTone(score)
  return (
    <Badge variant="outline" className={cn('shrink-0 font-semibold', tone && toneBg[tone], tone && toneText[tone])}>
      {score === null ? label : `${score} · ${label}`}
    </Badge>
  )
}

/** One outlet: its score, and (expandable) how each part of it was worked out. */
function SourceRow({ profile }: { profile: SourceProfile }) {
  return (
    <li className="rounded-lg border bg-background/50 px-3 py-2.5">
      <details className="group">
        <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
          <span className="min-w-0">
            <span className="text-sm font-semibold">{profile.source}</span>
            <span className="ml-2 text-xs text-muted-foreground">{profile.articles} reports</span>
          </span>
          <ScoreBadge score={profile.score} label={profile.label} />
        </summary>
        <ul className="mt-2.5 space-y-2 border-t pt-2.5">
          {profile.breakdown.map((c) => (
            <li key={c.key} className="space-y-0.5">
              <div className="flex items-baseline justify-between text-xs">
                <span className="font-medium">{c.label}</span>
                <span className="text-muted-foreground tabular-nums">{c.points === null ? 'not enough data' : `${c.points} / ${c.max}`}</span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-link/70" style={{ width: c.points === null ? 0 : `${(c.points / c.max) * 100}%` }} />
              </div>
              <p className="text-[11.5px] leading-snug text-muted-foreground">{c.detail}</p>
            </li>
          ))}
          {profile.first_report_rate !== null && (
            <li className="text-[11.5px] text-muted-foreground">
              First to report {percent(profile.first_report_rate)} of the events it covers alongside others (shown for context, not scored).
            </li>
          )}
        </ul>
      </details>
    </li>
  )
}

/** The sources dialog. */
export function SourcesDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [data, setData] = useState<SourceList | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    let live = true
    api.sources().then(
      (d) => live && (setData(d), setError('')),
      (e: Error) => live && setError(e.message),
    )
    return () => {
      live = false
    }
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="size-4 text-link" aria-hidden /> Source profiles
          </DialogTitle>
          <DialogDescription>
            {data?.note ?? 'How each outlet publishes, worked out from the articles SignalDesk has read. Not an editorial rating.'}
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-96 pr-3">
          {error && <p className="text-sm text-negative">Could not load the profiles: {error}</p>}
          {!error && !data && <Skeleton className="h-40 w-full" />}
          {data && (
            <ul className="space-y-2">
              {data.items.map((p) => (
                <SourceRow key={p.source} profile={p} />
              ))}
              {data.items.length === 0 && <li className="text-sm text-muted-foreground">No articles yet. Run an ingest first.</li>}
            </ul>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
