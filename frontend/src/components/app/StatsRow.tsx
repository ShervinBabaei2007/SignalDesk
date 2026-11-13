import type { ReactNode } from 'react'
import { BlurFade } from '@/components/ui/blur-fade'
import { Card, CardContent } from '@/components/ui/card'
import { NumberTicker } from '@/components/ui/number-ticker'
import { Skeleton } from '@/components/ui/skeleton'
import { SentimentInfo, toneText } from '@/components/app/Sentiment'
import { useDashboard } from '@/hooks/useDashboard'
import { describeAverage, describeSentiment, formatScore } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

function Stat({ label, children, delay, className }: { label: ReactNode; children: ReactNode; delay: number; className?: string }) {
  return (
    <BlurFade delay={delay} className={className}>
      <Card className="h-full gap-1 py-4">
        <CardContent className="px-4">
          <div className="flex items-center gap-1 text-[13px] font-medium text-muted-foreground">{label}</div>
          {children}
        </CardContent>
      </Card>
    </BlurFade>
  )
}

function TrendChart({ points }: { points: { avg_sentiment: number }[] }) {
  if (points.length < 2) {
    return <p className="mt-4 text-xs text-muted-foreground">Collecting data…</p>
  }
  const vals = points.map((p) => p.avg_sentiment)
  const min = Math.min(...vals, -0.3)
  const max = Math.max(...vals, 0.3)
  const range = max - min || 1
  const w = 220, h = 60, pad = 4
  const coords = vals.map((v, i) => [pad + (i / (vals.length - 1)) * (w - pad * 2), h - pad - ((v - min) / range) * (h - pad * 2)])
  const line = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${coords.at(-1)![0].toFixed(1)},${h} L${coords[0][0].toFixed(1)},${h} Z`
  const zeroY = h - pad - ((0 - min) / range) * (h - pad * 2)
  const last = vals.at(-1)!
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn('mt-2 h-14 w-full', toneText[describeSentiment(last).tone])} role="img" aria-label="Average sentiment per day over the last 7 days">
      <line x1="0" x2={w} y1={zeroY} y2={zeroY} className="stroke-border" strokeDasharray="3 4" />
      <path d={area} fill="currentColor" opacity="0.1" />
      <path d={line} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={coords.at(-1)![0]} cy={coords.at(-1)![1]} r="3" fill="currentColor" />
    </svg>
  )
}

export function StatsRow() {
  const { stats } = useDashboard()
  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className={cn('h-28 rounded-xl', i === 4 && 'col-span-2 lg:col-span-1')} />
        ))}
      </div>
    )
  }
  const tone = describeSentiment(stats.avg_sentiment).tone
  const total = Math.max(stats.positive + stats.neutral + stats.negative, 1)
  const value = 'mt-1 block text-3xl font-bold tracking-tight tabular-nums'
  return (
    <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
      <Stat label="Total articles" delay={0}>
        <NumberTicker value={stats.total_articles} className={value} />
      </Stat>
      <Stat label="Sources" delay={0.05}>
        <NumberTicker value={stats.total_sources} className={value} />
      </Stat>
      <Stat label="Last 24 hours" delay={0.1}>
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
      <Stat label="Sentiment trend (7 days)" delay={0.2} className="compact-hide col-span-2 lg:col-span-1">
        <TrendChart points={stats.sentiment_7d} />
      </Stat>
    </div>
  )
}
