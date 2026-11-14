// Collapsible list of a story's ranked reports.
import { ArrowRight, ChevronDown, Layers } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { AppLink as Link } from '@/components/app/AppLink'
import { InfoScore } from '@/components/app/InfoScore'
import { SentimentBadge } from '@/components/app/Sentiment'
import { SourceAvatar } from '@/components/app/AlsoCoveredBy'
import type { ReportBrief } from '@/lib/api'
import { timeAgo } from '@/lib/format'

/** One report: outlet, headline, how much information it carries, and its wording. */
export function ReportRow({ report: r, rank, best }: { report: ReportBrief; rank?: number; best?: boolean }) {
  return (
    <Link
      to={`/article/${r.id}`}
      className="group/row flex items-center gap-3 rounded-lg border bg-background/50 px-3 py-2 transition-colors hover:border-foreground/20 hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {rank !== undefined && (
        <span className="grid size-5 shrink-0 place-items-center rounded-md bg-muted text-[11px] font-semibold text-muted-foreground tabular-nums">
          {rank}
        </span>
      )}
      <SourceAvatar name={r.source} size="default" />
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-[13px] leading-snug font-medium group-hover/row:text-link">{r.title}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">{r.source}</span>
          <span>·</span>
          <span>{timeAgo(r.published_at)}</span>
          {best && <span className="font-semibold text-link">· Best coverage</span>}
        </span>
      </span>
      <InfoScore score={r.info_score} variant="bar" className="hidden sm:inline-flex" />
      <span className="hidden w-28 justify-end md:flex">
        <SentimentBadge score={r.sentiment} />
      </span>
    </Link>
  )
}

/** The other outlets' reports of a story, already ordered best-informed first. */
export function StoryReports({
  others, defaultOpen = false, clusterId = null,
}: { others: ReportBrief[]; defaultOpen?: boolean; clusterId?: number | null }) {
  if (!others.length) return null
  const outlets = new Set(others.map((o) => o.source)).size
  return (
    // Clicks in here must not trigger the card's own "open article" click.
    <Collapsible defaultOpen={defaultOpen} onClick={(e) => e.stopPropagation()} className="border-t pt-2.5">
      <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md px-1 py-1 text-left text-sm font-medium text-link transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
        <Layers className="size-4" aria-hidden />
        <span>
          {others.length} more {others.length === 1 ? 'report' : 'reports'}
          <span className="font-normal text-muted-foreground">
            {' '}
            from {outlets} other {outlets === 1 ? 'outlet' : 'outlets'}, best-informed first
          </span>
        </span>
        <ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-data-[panel-open]:rotate-180" aria-hidden />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mt-2 space-y-1.5">
          {others.map((r) => (
            <li key={r.id}>
              <ReportRow report={r} />
            </li>
          ))}
        </ol>
        {clusterId != null && (
          <Link
            to={`/story/${clusterId}`}
            className="mt-2 inline-flex items-center gap-1 rounded-md px-1 py-1 text-sm font-medium text-link hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            Open the full story: brief and outlet comparison <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
