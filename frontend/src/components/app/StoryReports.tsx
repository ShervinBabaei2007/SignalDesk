import { ChevronDown, Newspaper } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { InfoScore } from '@/components/app/InfoScore'
import { SentimentBadge } from '@/components/app/Sentiment'
import { SourceAvatar } from '@/components/app/AlsoCoveredBy'
import type { ReportBrief } from '@/lib/api'
import { timeAgo } from '@/lib/format'

/** The other outlets' reports of a story, already ordered best-informed first. */
export function StoryReports({
  others, defaultOpen = false,
}: { others: ReportBrief[]; defaultOpen?: boolean }) {
  if (!others.length) return null
  const outlets = new Set(others.map((o) => o.source)).size
  return (
    // Clicks in here must not trigger the card's own "open article" click.
    <Collapsible defaultOpen={defaultOpen} onClick={(e) => e.stopPropagation()} className="border-t pt-2.5">
      <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md px-1 py-1 text-left text-sm font-medium text-link transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
        <Newspaper className="size-4" aria-hidden />
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
              <a
                href={`#/article/${r.id}`}
                className="group/row flex items-center gap-3 rounded-lg border bg-background/50 px-3 py-2 transition-colors hover:border-foreground/20 hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <SourceAvatar name={r.source} size="default" />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 text-[13px] leading-snug font-medium group-hover/row:text-link">{r.title}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    <span className="font-medium text-foreground/80">{r.source}</span> · {timeAgo(r.published_at)}
                  </span>
                </span>
                <InfoScore score={r.info_score} variant="bar" className="hidden sm:inline-flex" />
                <span className="hidden w-28 justify-end md:flex">
                  <SentimentBadge score={r.sentiment} />
                </span>
              </a>
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  )
}
