// Panel listing the hot stories when the Hot topics category is selected.
import { Flame } from 'lucide-react'
import { BlurFade } from '@/components/ui/blur-fade'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ToneIcon, toneText } from '@/components/app/Sentiment'
import { useDashboard } from '@/hooks/useDashboard'
import { timeAgo } from '@/lib/format'
import { describeSentiment } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

/** Shown above the feed while the "Hot topics" category is selected: the stories
 *  the most outlets are covering right now. Picking one narrows the feed to it. */
export function HotStories() {
  const { trending, openStory } = useDashboard()
  return (
    <BlurFade duration={0.3} offset={6}>
      <Card className="mb-3 gap-3">
        <CardHeader className="gap-1">
          <CardTitle className="flex items-center gap-2 text-[15px]">
            <Flame className="size-4 text-amber-500" aria-hidden /> Hot topics
          </CardTitle>
          <CardDescription>
            The stories the most outlets are covering right now. The articles below are all part of them; pick one to read every
            report of that story.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trending.length === 0 ? (
            <p className="text-sm text-muted-foreground">No big stories yet. Run an ingest to find out what everyone is covering.</p>
          ) : (
            <ol className="grid gap-1.5 md:grid-cols-2">
              {trending.map((t, i) => {
                const tone = describeSentiment(t.avg_sentiment)
                return (
                  <li key={t.cluster_id}>
                    <button
                      type="button"
                      onClick={() => {
                        openStory(t.cluster_id)
                        window.scrollTo({ top: 0, behavior: 'smooth' })
                      }}
                      className="group flex h-full w-full items-start gap-2.5 rounded-lg border bg-background/50 px-3 py-2.5 text-left transition-colors hover:border-foreground/20 hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                    >
                      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-md bg-muted text-[11px] font-semibold text-muted-foreground tabular-nums">
                        {i + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 text-[13.5px] leading-snug font-medium group-hover:text-link">{t.title}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[11.5px] text-muted-foreground">
                          <span className="font-medium text-foreground/80">{t.outlets} outlets</span>
                          <span>·</span>
                          <span>{t.reports} reports</span>
                          <span>·</span>
                          <span>{timeAgo(t.latest_at)}</span>
                          {(t.days_active ?? 1) > 1 && (
                            <span className="font-medium text-foreground/80" title="How long this event has been in the news">
                              · active {t.days_active} days
                            </span>
                          )}
                          <span className={cn('inline-flex items-center gap-0.5', toneText[tone.tone])} title={`${tone.label} wording`}>
                            <ToneIcon tone={tone.tone} className="size-2.5" />
                          </span>
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          )}
        </CardContent>
      </Card>
    </BlurFade>
  )
}
