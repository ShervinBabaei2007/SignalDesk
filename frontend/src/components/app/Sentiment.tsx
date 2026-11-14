// Shared sentiment visuals: tone colours, icons, badge and gauge.
import { ArrowDown, ArrowUp, Info, Minus, type LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { describeSentiment, SENTIMENT_LEVELS, scalePosition, type Tone } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

/** Text colour class per sentiment tone. */
export const toneText: Record<Tone, string> = {
  positive: 'text-positive',
  neutral: 'text-neutral',
  negative: 'text-negative',
}
/** Background and border classes per sentiment tone. */
export const toneBg: Record<Tone, string> = {
  positive: 'bg-positive/12 border-positive/30',
  neutral: 'bg-neutral/12 border-neutral/30',
  negative: 'bg-negative/12 border-negative/30',
}

/** Icon per sentiment tone. */
const toneIcon: Record<Tone, LucideIcon> = {
  positive: ArrowUp,
  neutral: Minus,
  negative: ArrowDown,
}

/** Arrow icon for a sentiment tone. */
export function ToneIcon({ tone, className }: { tone: Tone; className?: string }) {
  const Icon = toneIcon[tone]
  return <Icon className={cn('size-3', className)} aria-hidden />
}

/** Badge showing the tone in plain words; the tooltip explains it and shows the score. */
export function SentimentBadge({ score, className }: { score: number; className?: string }) {
  const d = describeSentiment(score)
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            variant="outline"
            className={cn('cursor-help gap-1 font-semibold', toneBg[d.tone], toneText[d.tone], className)}
          />
        }
      >
        <ToneIcon tone={d.tone} />
        {d.label}
      </TooltipTrigger>
      <TooltipContent className="max-w-64 flex-col items-start gap-0.5 py-2 text-left">
        <span className="font-semibold">
          {d.label} · {d.score}
        </span>
        <span className="font-normal opacity-90">{d.blurb}</span>
      </TooltipContent>
    </Tooltip>
  )
}

/** The −1…+1 scale as three colour zones, with an optional marker. */
export function SentimentScale({ score, className }: { score?: number; className?: string }) {
  return (
    <div className={className}>
      <div className="relative h-2 rounded-full bg-[linear-gradient(90deg,color-mix(in_srgb,var(--negative)_55%,transparent)_0_42.5%,color-mix(in_srgb,var(--neutral)_45%,transparent)_42.5%_57.5%,color-mix(in_srgb,var(--positive)_55%,transparent)_57.5%_100%)]">
        {score !== undefined && (
          <span
            className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-card bg-foreground shadow transition-[left] duration-500"
            style={{ left: `${scalePosition(score)}%` }}
          />
        )}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-muted-foreground">
        <span>−1 Negative</span>
        <span>0</span>
        <span>Positive +1</span>
      </div>
    </div>
  )
}

/** Professional "what does this mean?" affordance: an Info icon button that opens a popover. */
export function SentimentInfo({ className }: { className?: string }) {
  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger
          render={
            <PopoverTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="What does sentiment mean?"
                  className={cn('rounded-full text-muted-foreground hover:text-foreground', className)}
                />
              }
            />
          }
        >
          <Info />
        </TooltipTrigger>
        <TooltipContent>What does sentiment mean?</TooltipContent>
      </Tooltip>
      <PopoverContent align="start" className="w-[min(24rem,calc(100vw-2rem))] gap-3 p-4">
        <PopoverHeader>
          <PopoverTitle className="text-base">How positive or negative are the words?</PopoverTitle>
          <PopoverDescription className="text-[13px] leading-relaxed">
            SignalDesk counts words like <em>win, growth, success</em> (positive) and <em>crash, fail, attack</em>{' '}
            (negative), then scores the article from <strong>−1</strong> (all negative) to <strong>+1</strong> (all
            positive). <strong>0</strong> means balanced.
          </PopoverDescription>
        </PopoverHeader>
        <SentimentScale />
        <ul className="divide-y divide-border overflow-hidden rounded-lg border">
          {SENTIMENT_LEVELS.map((l) => (
            <li key={l.label} className="flex items-start gap-3 px-3 py-2">
              <Badge variant="outline" className={cn('mt-0.5 w-28 shrink-0 justify-center gap-1', toneBg[l.tone], toneText[l.tone])}>
                <ToneIcon tone={l.tone} />
                {l.label}
              </Badge>
              <div className="min-w-0 text-[12.5px] leading-snug">
                <div className="font-mono text-[11px] text-muted-foreground">{l.range}</div>
                {l.blurb}
              </div>
            </li>
          ))}
        </ul>
        <p className="rounded-lg bg-muted px-3 py-2 text-[12.5px] leading-relaxed text-muted-foreground">
          <strong className="text-foreground">Keep in mind:</strong> the score is about the <em>words</em>, not the
          facts. A calm report about a disaster can still score Neutral, and it can’t detect sarcasm. Use it as a quick
          hint, not a verdict.
        </p>
      </PopoverContent>
    </Popover>
  )
}
