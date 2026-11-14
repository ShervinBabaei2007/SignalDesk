// "Get started" checklist at the top of the dashboard in the demo and in a workspace.
import { Check, Circle, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useMode } from '@/hooks/useMode'
import { navigateAbsolute, openTool } from '@/lib/nav'
import type { PrefixMode } from '@/lib/mode'
import { progress, setDismissed, STEPS, useOnboarding } from '@/lib/onboarding'
import { cn } from '@/lib/utils'

/** The checklist's heading for a mode and how far along it is. */
function heading(mode: PrefixMode, complete: boolean): string {
  if (complete) return 'You’re all set'
  return mode === 'demo' ? 'Take the tour' : 'Get your workspace going'
}

/** The dismissible checklist for the current mode; renders nothing when browsing, as the owner, or once hidden. */
export function GetStartedCard() {
  const { prefix } = useMode()
  const state = useOnboarding(prefix ?? 'demo')
  if (!prefix || state.dismissed) return null

  const { done, total } = progress(prefix, state.done)
  const complete = done === total

  return (
    <Card className="mb-4">
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold">
              {heading(prefix, complete)}
            </h2>
            <p className="text-[13px] text-muted-foreground">
              {done} of {total} done
              {prefix === 'demo' && complete ? ' · Open a workspace to add your own feeds and alerts.' : ''}
            </p>
          </div>
          <Button variant="ghost" size="icon-sm" aria-label="Hide checklist" title="Hide checklist" onClick={() => setDismissed(prefix, true)}>
            <X />
          </Button>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
          <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${(done / total) * 100}%` }} />
        </div>
        <ul className="grid gap-1.5 sm:grid-cols-2">
          {STEPS[prefix].map((s) => {
            const isDone = state.done.includes(s.id)
            const action = s.action
            return (
              <li key={s.id} className="flex items-start gap-2.5 rounded-lg border bg-background/50 px-3 py-2">
                {isDone ? (
                  <Check className="mt-0.5 size-4 shrink-0 text-positive" aria-label="Done" />
                ) : (
                  <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                )}
                <div className="min-w-0 flex-1">
                  <p className={cn('text-sm font-medium', isDone && 'text-muted-foreground line-through')}>{s.title}</p>
                  <p className="text-xs text-muted-foreground">{s.hint}</p>
                </div>
                {action && !isDone && (
                  <Button size="sm" variant="outline" onClick={() => openTool(action.tool)}>{action.label}</Button>
                )}
              </li>
            )
          })}
        </ul>
        {prefix === 'demo' && (
          <Button size="sm" onClick={() => navigateAbsolute('/workspace')}>Open a workspace</Button>
        )}
      </CardContent>
    </Card>
  )
}
