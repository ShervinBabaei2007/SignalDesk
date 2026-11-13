import type { ReactNode } from 'react'
import { BlurFade } from '@/components/ui/blur-fade'
import { Card, CardContent } from '@/components/ui/card'
import { NumberTicker } from '@/components/ui/number-ticker'
import { Skeleton } from '@/components/ui/skeleton'
import { SentimentInfo, toneText } from '@/components/app/Sentiment'
import { TrendCard } from '@/components/app/TrendCard'
import { useDashboard } from '@/hooks/useDashboard'
import { describeAverage, describeSentiment, formatScore } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

function Stat({
  label, children, delay, caption, className,
}: { label: ReactNode; children: ReactNode; delay: number; caption?: string; className?: string }) {
  return (
    <BlurFade delay={delay} className={cn('h-full', className)}>
      <Card className="h-full gap-1 py-4">
        <CardContent className="flex h-full flex-col justify-between gap-3 px-4">
          <div className="flex items-center gap-1 text-[13px] font-medium text-muted-foreground">{label}</div>
          <div>
            {children}
            {caption && <span className="mt-1 block text-xs text-muted-foreground">{caption}</span>}
          </div>
        </CardContent>
      </Card>
    </BlurFade>
  )
}

export function StatsRow() {
  const { stats } = useDashboard()
  if (!stats) {
    return (
      <div className="grid gap-2.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="grid grid-cols-2 gap-2.5">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-60 rounded-xl" />
      </div>
    )
  }
  const tone = describeSentiment(stats.avg_sentiment).tone
  const total = Math.max(stats.positive + stats.neutral + stats.negative, 1)
  const value = 'mt-1 block text-3xl font-bold tracking-tight tabular-nums'
  return (
    <div className="stats-grid grid gap-2.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="stats-kpis grid grid-cols-2 gap-2.5">
      <Stat label="Total articles" delay={0} caption="collected so far">
        <NumberTicker value={stats.total_articles} className={value} />
      </Stat>
      <Stat label="Sources" delay={0.05} caption="news outlets read">
        <NumberTicker value={stats.total_sources} className={value} />
      </Stat>
      <Stat label="Last 24 hours" delay={0.1} caption="new in the past day">
        <NumberTicker value={stats.ingested_last_24h} className={value} />
      </Stat>
      <Stat
        label={
          <>
            Average sentiment <SentimentInfo />
          </>
        }
        delay={0.15}
      >
        <span className={cn('mt-1 block text-xl leading-tight font-bold tracking-tight', toneText[tone])}>
          {describeAverage(stats.avg_sentiment)}
        </span>
        <span className="mt-0.5 block text-xs text-muted-foreground">Score {formatScore(stats.avg_sentiment)} (−1 to +1)</span>
        <div className="mt-2.5 flex h-1.5 gap-0.5 overflow-hidden rounded-full" aria-label={`${stats.positive} positive, ${stats.neutral} neutral, ${stats.negative} negative`}>
          <span className="bg-positive transition-[width] duration-500" style={{ width: `${(stats.positive / total) * 100}%` }} />
          <span className="bg-neutral transition-[width] duration-500" style={{ width: `${(stats.neutral / total) * 100}%` }} />
          <span className="bg-negative transition-[width] duration-500" style={{ width: `${(stats.negative / total) * 100}%` }} />
        </div>
      </Stat>
      </div>
      <BlurFade delay={0.2} className="compact-hide">
        <TrendCard points={stats.sentiment_7d} />
      </BlurFade>
    </div>
  )
}
