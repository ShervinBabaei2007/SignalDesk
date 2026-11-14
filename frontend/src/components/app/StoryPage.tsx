import { useEffect, useState } from 'react'
import { ArrowLeft, Check, GitCompareArrows, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { BlurFade } from '@/components/ui/blur-fade'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { OutletComparison } from '@/components/app/OutletComparison'
import { ReportRow } from '@/components/app/StoryReports'
import { SentimentBadge } from '@/components/app/Sentiment'
import { api, ApiError, type StoryBrief, type StoryDetail } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

function BriefCard({ brief, onRefresh, refreshing }: { brief: StoryBrief; onRefresh: () => void; refreshing: boolean }) {
  const ai = brief.kind === 'ai'
  return (
    <Card className="border-ai/35 bg-ai/5">
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold">
            <Sparkles className="size-4 text-ai" aria-hidden /> Story brief
            <Badge variant="outline" className={cn('font-medium', ai ? 'border-ai/40 text-ai' : 'text-muted-foreground')}>
              {ai ? `AI-written${brief.model ? ` · ${brief.model}` : ''}` : 'Auto summary'}
            </Badge>
          </h2>
          <Button variant="ghost" size="sm" onClick={onRefresh} disabled={refreshing} title="Rewrite this brief from the latest reports">
            {refreshing ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <RefreshCw data-icon="inline-start" />}
            Refresh
          </Button>
        </div>

        <p className="text-base leading-snug font-semibold">{brief.headline}</p>

        <div className="grid gap-4 md:grid-cols-2">
          <section aria-labelledby="agree">
            <h3 id="agree" className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-positive uppercase">
              <Check className="size-3.5" aria-hidden /> What everyone agrees on
            </h3>
            <ul className="space-y-1.5 text-[13.5px] leading-relaxed">
              {brief.agree.map((line, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-positive" aria-hidden />
                  {line}
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="differ">
            <h3 id="differ" className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-amber-500 uppercase">
              <GitCompareArrows className="size-3.5" aria-hidden /> Where outlets differ
            </h3>
            <ul className="space-y-1.5 text-[13.5px] leading-relaxed">
              {brief.differ.map((line, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-500" aria-hidden />
                  {line}
                </li>
              ))}
            </ul>
          </section>
        </div>

        <p className="text-xs text-muted-foreground">
          {ai
            ? 'Written by a language model that was given only these reports.'
            : 'Written automatically from the reports: figures several outlets cite, points they back up, and where wording differs.'}
          {brief.generated_at ? ` Updated ${timeAgo(brief.generated_at)}.` : ''}
        </p>
      </CardContent>
    </Card>
  )
}

function StorySkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-9 w-3/4" />
      <Skeleton className="h-52 w-full rounded-xl" />
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  )
}

/** One event in depth: the brief, how each outlet covered it, and every report ranked. */
export function StoryPage({ id }: { id: number }) {
  const [story, setStory] = useState<StoryDetail | null>(null)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    setStory(null)
    setError('')
    window.scrollTo({ top: 0 })
    let live = true
    api.story(id).then(
      (s) => live && setStory(s),
      (e: Error) => live && setError(e.message),
    )
    return () => {
      live = false
    }
  }, [id])

  const refresh = async () => {
    setRefreshing(true)
    try {
      setStory(await api.refreshBrief(id))
      toast.success('Brief rewritten')
    } catch (err) {
      const e = err as ApiError
      toast.error(e.status === 401 ? 'Add your API token in Settings first' : `Could not refresh: ${e.message}`)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Button variant="ghost" className="-ml-2" render={<a href="#/" />}>
        <ArrowLeft data-icon="inline-start" /> Back to feed
      </Button>

      {error ? (
        <Card className="py-12 text-center">
          <h2 className="text-lg font-semibold">Story not found</h2>
          <p className="text-sm text-muted-foreground">{error}</p>
        </Card>
      ) : !story ? (
        <StorySkeleton />
      ) : (
        <>
          <BlurFade>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary">
                {story.report_count} reports · {story.outlets} outlets
              </Badge>
              <SentimentBadge score={story.avg_sentiment} />
              {story.sentiment_spread >= 0.3 && (
                <Badge variant="outline" title="The most and least positive wording differ by this much on the −1 to +1 scale">
                  Wording varies · spread {story.sentiment_spread.toFixed(2)}
                </Badge>
              )}
            </div>
            <h1 className="mt-2 text-2xl leading-tight font-bold tracking-tight sm:text-3xl">{story.title}</h1>
          </BlurFade>

          <BlurFade delay={0.05}>
            <BriefCard brief={story.brief} onRefresh={() => void refresh()} refreshing={refreshing} />
          </BlurFade>

          <BlurFade delay={0.1}>
            <OutletComparison rows={story.comparison} />
          </BlurFade>

          <BlurFade delay={0.15}>
            <Card>
              <CardContent className="space-y-3">
                <div>
                  <h2 className="text-[15px] font-semibold">All reports, best-informed first</h2>
                  <p className="text-sm text-muted-foreground">Open any report to read its summary and key points.</p>
                </div>
                <ol className="space-y-1.5">
                  {story.reports.map((r, i) => (
                    <li key={r.id}>
                      <ReportRow report={r} rank={i + 1} best={i === 0 && story.reports.length > 1} />
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </BlurFade>
        </>
      )}
    </div>
  )
}
