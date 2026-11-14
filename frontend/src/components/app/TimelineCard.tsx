// How coverage of the story's event developed day by day.
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { StoryTimeline } from '@/lib/api'
import { barHeights, dayInitial, dayLabel } from '@/lib/insights'
import { describeSentiment, formatScore } from '@/lib/sentiment'
import { toneText } from '@/components/app/Sentiment'
import { cn } from '@/lib/utils'

/** The reports-per-day chart with the tone of each day underneath. */
function DayBars({ timeline }: { timeline: StoryTimeline }) {
  const heights = barHeights(timeline.days.map((d) => d.reports))
  return (
    <ol className="flex h-28 items-end gap-1.5" aria-label="Reports per day">
      {timeline.days.map((d, i) => {
        const tone = d.avg_sentiment === null ? null : describeSentiment(d.avg_sentiment)
        return (
          <li key={d.date} className="flex h-full min-w-0 flex-1 flex-col justify-end gap-1">
            <Tooltip>
              <TooltipTrigger
                render={<div tabIndex={0} className="flex min-h-0 flex-1 cursor-help flex-col justify-end outline-none" aria-label={`${dayLabel(d.date)}: ${d.reports} reports from ${d.outlets} outlets`} />}
              >
                {/* Days with no reports keep a 3px stub so the day still shows */}
                <div
                  className={cn('w-full rounded-t-sm', d.reports ? 'bg-link/70' : 'bg-muted')}
                  style={{ height: d.reports ? `${heights[i]}%` : '3px' }}
                />
              </TooltipTrigger>
              <TooltipContent>
                <div className="font-semibold">{dayLabel(d.date)}</div>
                <div>
                  {d.reports} report{d.reports === 1 ? '' : 's'} · {d.outlets} outlet{d.outlets === 1 ? '' : 's'}
                </div>
                {tone && d.avg_sentiment !== null && (
                  <div>
                    {tone.label} ({formatScore(d.avg_sentiment)})
                  </div>
                )}
                {d.new_outlets.length > 0 && <div>New: {d.new_outlets.join(', ')}</div>}
              </TooltipContent>
            </Tooltip>
            <span className="text-center text-[10px] text-muted-foreground">{dayInitial(d.date)}</span>
            <span
              className={cn('mx-auto size-1.5 rounded-full', tone ? 'bg-current' : 'bg-transparent', tone && toneText[tone.tone])}
              aria-hidden
            />
          </li>
        )
      })}
    </ol>
  )
}

/** Day-by-day coverage of the event this story belongs to. */
export function TimelineCard({ timeline }: { timeline: StoryTimeline }) {
  const multiDay = timeline.days_active > 1
  const shift = timeline.sentiment_shift
  // Days on which at least one outlet covered the story for the first time.
  const joined = timeline.days.filter((d) => d.new_outlets.length > 0)
  return (
    <Card>
      <CardHeader className="gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-[15px]">How coverage developed</CardTitle>
          <Badge variant="secondary">
            {multiDay ? `Active ${timeline.days_active} days` : 'First day of coverage'}
          </Badge>
        </div>
        <CardDescription>
          {timeline.first_reported_by ? `First reported by ${timeline.first_reported_by}. ` : ''}
          {timeline.reports} report{timeline.reports === 1 ? '' : 's'} from {timeline.outlets} outlet{timeline.outlets === 1 ? '' : 's'}
          {/* Only tone shifts of 0.1 or more over several days are worth mentioning */}
          {multiDay && Math.abs(shift) >= 0.1
            ? `; the tone moved ${shift > 0 ? 'more positive' : 'more negative'} (${shift > 0 ? '+' : '−'}${Math.abs(shift).toFixed(2)}).`
            : '.'}
        </CardDescription>
      </CardHeader>
      {multiDay && (
        <CardContent className="space-y-3">
          <DayBars timeline={timeline} />
          {joined.length > 0 && (
            <ul className="space-y-1 text-xs text-muted-foreground">
              {joined.map((d) => (
                <li key={d.date}>
                  <span className="font-medium text-foreground/80">{dayLabel(d.date)}</span> · joined: {d.new_outlets.join(', ')}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      )}
    </Card>
  )
}
