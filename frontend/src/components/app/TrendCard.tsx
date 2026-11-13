import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { SentimentInfo, toneBg, toneText } from '@/components/app/Sentiment'
import type { Stats } from '@/lib/api'
import { monotonePath } from '@/lib/chart'
import { describeSentiment, formatScore } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

type Point = Stats['sentiment_7d'][number]

const W = 480
const H = 168
const PAD = { l: 8, r: 8, t: 14, b: 26 }
const TONE_FILL = { positive: 'var(--positive)', neutral: 'var(--neutral)', negative: 'var(--negative)' }

function dayLabel(date: string, long = false): string {
  const d = new Date(`${date}T00:00:00Z`)
  return d.toLocaleDateString(
    undefined,
    long ? { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' } : { weekday: 'short', timeZone: 'UTC' },
  )
}

/** The 7-day sentiment trend: smooth line, colour-coded points, sentiment zones and a hover readout. */
export function TrendCard({ points, className }: { points: Point[]; className?: string }) {
  const reduce = useReducedMotion()
  const [hover, setHover] = useState<number | null>(null)

  const chart = useMemo(() => {
    const vals = points.map((p) => p.avg_sentiment)
    const lo = Math.min(-0.4, Math.min(...vals) - 0.08)
    const hi = Math.max(0.4, Math.max(...vals) + 0.08)
    const x = (i: number) =>
      PAD.l + (points.length === 1 ? (W - PAD.l - PAD.r) / 2 : (i / (points.length - 1)) * (W - PAD.l - PAD.r))
    const y = (v: number) => PAD.t + ((hi - v) / (hi - lo)) * (H - PAD.t - PAD.b)
    const coords = points.map((p, i) => [x(i), y(p.avg_sentiment)] as [number, number])
    const line = monotonePath(coords)
    const base = H - PAD.b
    const area =
      coords.length > 1
        ? `${line} L${coords[coords.length - 1][0].toFixed(1)},${base} L${coords[0][0].toFixed(1)},${base} Z`
        : ''
    return { coords, line, area, zero: y(0), posEdge: y(0.15), negEdge: y(-0.15), top: PAD.t, base }
  }, [points])

  if (points.length < 2) {
    return (
      <Card className={cn('h-full', className)}>
        <CardHeader>
          <CardTitle className="text-[15px]">Sentiment trend</CardTitle>
          <CardDescription>Needs at least two days of articles. Check back after the next ingest.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const activeIdx = hover ?? points.length - 1
  const active = points[activeIdx]
  const level = describeSentiment(active.avg_sentiment)
  const prev = activeIdx > 0 ? points[activeIdx - 1] : null
  const delta = prev ? active.avg_sentiment - prev.avg_sentiment : 0
  const steady = !prev || Math.abs(delta) < 0.02
  const DeltaIcon = steady ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight
  const leftPct = (chart.coords[activeIdx][0] / W) * 100
  const innerW = W - PAD.l - PAD.r

  return (
    <Card className={cn('h-full gap-3', className)}>
      <CardHeader className="gap-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-1 text-[15px]">
              Sentiment trend <SentimentInfo />
            </CardTitle>
            <CardDescription>Daily average, last 7 days</CardDescription>
          </div>
          <div className="text-right" aria-live="polite">
            <Badge variant="outline" className={cn('font-semibold', toneBg[level.tone], toneText[level.tone])}>
              {level.label} · {formatScore(active.avg_sentiment)}
            </Badge>
            <div className="mt-1 flex items-center justify-end gap-1 text-xs text-muted-foreground">
              <span>{activeIdx === points.length - 1 ? 'Latest' : dayLabel(active.date)}</span>
              {prev && (
                <span className={cn('inline-flex items-center', !steady && (delta > 0 ? 'text-positive' : 'text-negative'))}>
                  <DeltaIcon className="size-3.5" aria-hidden />
                  {steady ? 'steady' : `${delta > 0 ? '+' : '−'}${Math.abs(delta).toFixed(2)}`}
                </span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full overflow-visible"
          role="group"
          aria-label="Average sentiment per day, last 7 days"
        >
          <defs>
            <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--link)" stopOpacity="0.32" />
              <stop offset="100%" stopColor="var(--link)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* sentiment zones: positive above, neutral band, negative below */}
          <rect x={PAD.l} y={chart.top} width={innerW} height={Math.max(chart.posEdge - chart.top, 0)} fill="var(--positive)" opacity="0.07" rx="4" />
          <rect x={PAD.l} y={chart.posEdge} width={innerW} height={Math.max(chart.negEdge - chart.posEdge, 0)} fill="var(--neutral)" opacity="0.09" />
          <rect x={PAD.l} y={chart.negEdge} width={innerW} height={Math.max(chart.base - chart.negEdge, 0)} fill="var(--negative)" opacity="0.07" rx="4" />
          <line x1={PAD.l} x2={W - PAD.r} y1={chart.zero} y2={chart.zero} stroke="var(--border)" strokeDasharray="4 5" />
          <text x={W - PAD.r - 4} y={chart.zero - 4} textAnchor="end" className="fill-muted-foreground" fontSize="10">
            neutral
          </text>

          {hover !== null && (
            <line x1={chart.coords[hover][0]} x2={chart.coords[hover][0]} y1={chart.top} y2={chart.base} stroke="var(--border)" strokeWidth="1.5" />
          )}

          <path d={chart.area} fill="url(#trend-fill)" />
          <motion.path
            d={chart.line}
            fill="none"
            stroke="var(--link)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={reduce ? false : { pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1, ease: 'easeOut' }}
          />

          {points.map((p, i) => {
            const [cx, cy] = chart.coords[i]
            const lvl = describeSentiment(p.avg_sentiment)
            return (
              <g
                key={p.date}
                tabIndex={0}
                role="img"
                aria-label={`${dayLabel(p.date, true)}: ${lvl.label}, score ${formatScore(p.avg_sentiment)}${p.count ? `, ${p.count} articles` : ''}`}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                className="cursor-pointer outline-none"
              >
                <rect x={cx - W / points.length / 2} y={0} width={W / points.length} height={H} fill="transparent" />
                <circle cx={cx} cy={cy} r={i === activeIdx ? 6 : 4} fill={TONE_FILL[lvl.tone]} stroke="var(--card)" strokeWidth="2.5" />
              </g>
            )
          })}

          {points.map((p, i) => (
            <text
              key={`l-${p.date}`}
              x={chart.coords[i][0]}
              y={H - 6}
              textAnchor="middle"
              fontSize="11"
              className={cn(i === activeIdx ? 'fill-foreground font-semibold' : 'fill-muted-foreground')}
            >
              {dayLabel(p.date)}
            </text>
          ))}
        </svg>

        {hover !== null && (
          <div
            className="pointer-events-none absolute top-0 z-10 w-max max-w-44 -translate-x-1/2 rounded-lg border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-lg"
            style={{ left: `clamp(4.5rem, ${leftPct}%, calc(100% - 4.5rem))` }}
          >
            <div className="font-semibold">{dayLabel(active.date, true)}</div>
            <div className={cn('font-medium', toneText[level.tone])}>
              {level.label} · {formatScore(active.avg_sentiment)}
            </div>
            {active.count ? <div className="text-muted-foreground">{active.count} articles</div> : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
