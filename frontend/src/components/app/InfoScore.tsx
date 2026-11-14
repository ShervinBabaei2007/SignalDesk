import { Gauge } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { INFO_EXPLAINER, infoLevel } from '@/lib/info'
import { cn } from '@/lib/utils'

/** How much real information a report carries, as a badge or as a compact bar. */
export function InfoScore({
  score, variant = 'badge', className,
}: { score: number | null | undefined; variant?: 'badge' | 'bar'; className?: string }) {
  if (score === null || score === undefined) return null
  const level = infoLevel(score)
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          variant === 'badge' ? (
            <Badge variant="outline" tabIndex={0} className={cn('cursor-help gap-1 font-medium', level.text, className)} />
          ) : (
            <span tabIndex={0} className={cn('inline-flex cursor-help items-center gap-1.5 text-xs', className)} />
          )
        }
      >
        {variant === 'badge' ? (
          <>
            <Gauge className="size-3" aria-hidden />
            Info {level.value}
          </>
        ) : (
          <>
            <span className="h-1.5 w-14 overflow-hidden rounded-full bg-muted" aria-hidden>
              <span className={cn('block h-full rounded-full', level.bar)} style={{ width: `${level.value}%` }} />
            </span>
            <span className={cn('w-6 text-right font-mono tabular-nums', level.text)}>{level.value}</span>
          </>
        )}
      </TooltipTrigger>
      <TooltipContent className="max-w-64 flex-col items-start gap-0.5 py-2 text-left">
        <span className="font-semibold">
          {level.label} · information score {level.value}/100
        </span>
        <span className="font-normal opacity-90">{INFO_EXPLAINER}</span>
      </TooltipContent>
    </Tooltip>
  )
}
