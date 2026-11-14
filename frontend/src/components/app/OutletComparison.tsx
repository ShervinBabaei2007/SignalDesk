// Table-like comparison of how each outlet covered a story.
import { BlurFade } from '@/components/ui/blur-fade'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { AppLink as Link } from '@/components/app/AppLink'
import { SourceAvatar } from '@/components/app/AlsoCoveredBy'
import { InfoScore } from '@/components/app/InfoScore'
import { SentimentBadge, toneBg, toneText } from '@/components/app/Sentiment'
import type { OutletStat } from '@/lib/api'
import { sourceHue } from '@/lib/format'
import { cn } from '@/lib/utils'
import { reliabilityTone } from '@/lib/insights'
import { describeSentiment, formatScore, scalePosition } from '@/lib/sentiment'

/** Every outlet's wording on one −1…+1 line, so a difference in tone is visible at a glance. */
function SpreadLine({ rows }: { rows: OutletStat[] }) {
  return (
    <div>
      <div className="relative mx-2 h-9">
        {/* Gradient stops at 42.5% and 57.5% mark the neutral band in the middle of the scale */}
        <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-[linear-gradient(90deg,color-mix(in_srgb,var(--negative)_50%,transparent)_0_42.5%,color-mix(in_srgb,var(--neutral)_40%,transparent)_42.5%_57.5%,color-mix(in_srgb,var(--positive)_50%,transparent)_57.5%_100%)]" />
        {/* One lettered dot per outlet, placed at its sentiment score */}
        {rows.map((r, i) => {
          const hue = sourceHue(r.source)
          const level = describeSentiment(r.sentiment)
          return (
            <Tooltip key={r.source}>
              <TooltipTrigger
                render={
                  <span
                    tabIndex={0}
                    className="absolute top-1/2 grid size-6 cursor-help place-items-center rounded-full border-2 border-card text-[11px] font-bold shadow"
                    style={{
                      left: `${scalePosition(r.sentiment)}%`,
                      // stagger neighbours up and down so dots at similar scores stay readable
                      transform: `translate(-50%, ${i % 2 ? '-5%' : '-95%'})`,
                      background: `hsl(${hue} 70% 45%)`,
                      color: '#fff',
                    }}
                  />
                }
              >
                {r.source.charAt(0).toUpperCase()}
              </TooltipTrigger>
              <TooltipContent>
                {r.source}: {level.label} ({formatScore(r.sentiment)})
              </TooltipContent>
            </Tooltip>
          )
        })}
      </div>
      <div className="mx-2 flex justify-between text-[11px] text-muted-foreground">
        <span>−1 Negative</span>
        <span>0</span>
        <span>Positive +1</span>
      </div>
    </div>
  )
}

/** One outlet's row with its information, depth and wording. */
function Row({ row, index }: { row: OutletStat; index: number }) {
  // Rough word count, assuming about six characters per word including the space.
  const words = Math.round(row.chars / 6)
  const reliability = reliabilityTone(row.reliability)
  return (
    <BlurFade delay={0.04 * index} duration={0.3} offset={6}>
      <Link
        to={`/article/${row.report_id}`}
        className="group flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-background/50 px-3 py-2.5 transition-colors hover:border-foreground/20 hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span className="flex min-w-0 flex-1 basis-48 items-center gap-2.5">
          <SourceAvatar name={row.source} size="default" />
          <span className="min-w-0">
            <span className="block text-sm font-semibold group-hover:text-link">{row.source}</span>
            <span className="flex flex-wrap gap-1">
              {row.badges.map((b) => (
                <Badge key={b} variant="secondary" className="h-4 px-1.5 text-[10px] font-medium">
                  {b}
                </Badge>
              ))}
            </span>
          </span>
        </span>
        <InfoScore score={row.info_score} variant="bar" />
        {reliability !== null && (
          <Tooltip>
            <TooltipTrigger
              render={
                <span
                  className={cn(
                    'w-16 rounded-md border px-1.5 py-0.5 text-center text-[11px] font-semibold tabular-nums',
                    toneBg[reliability],
                    toneText[reliability],
                  )}
                />
              }
            >
              {row.reliability}/100
            </TooltipTrigger>
            <TooltipContent>
              {row.reliability_label}: how this outlet publishes (bylines, dates, sources, corrections), not whether it is right. Open Sources for the working.
            </TooltipContent>
          </Tooltip>
        )}
        <span className="w-24 text-xs text-muted-foreground tabular-nums">
          {words ? `≈ ${words.toLocaleString()} words` : 'excerpt only'}
        </span>
        <span className="w-24 text-xs text-muted-foreground tabular-nums">
          {row.numbers} figure{row.numbers === 1 ? '' : 's'} · {row.quotes} quote{row.quotes === 1 ? '' : 's'}
        </span>
        <SentimentBadge score={row.sentiment} />
      </Link>
    </BlurFade>
  )
}

/** Side-by-side look at how each outlet covered the same story. */
export function OutletComparison({ rows }: { rows: OutletStat[] }) {
  // best-informed first (the API already sorts, this keeps the component safe on its own)
  const ordered = [...rows].sort((a, b) => (b.info_score ?? 0) - (a.info_score ?? 0))
  return (
    <Card>
      <CardHeader className="gap-1">
        <CardTitle className="text-[15px]">How the outlets compare</CardTitle>
        <CardDescription>
          Each outlet’s best report on this story, most informative first. “Info” is how much real information it carries; the dots
          show how positive or negative its wording is.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {ordered.length > 1 && <SpreadLine rows={ordered} />}
        <div className="space-y-1.5">
          {ordered.map((r, i) => (
            <Row key={r.source} row={r} index={i} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
