import type { ReactNode } from 'react'
import { Bookmark, Flame } from 'lucide-react'
import { BlurFade } from '@/components/ui/blur-fade'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useDashboard } from '@/hooks/useDashboard'
import { useLibrary } from '@/hooks/useLibrary'
import { TOPIC_EMOJI } from '@/lib/format'
import { cn } from '@/lib/utils'

function CategoryRow({
  label, icon, count, max, active, hint, onClick,
}: { label: string; icon: ReactNode; count: number; max: number; active: boolean; hint?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      title={hint}
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
        active && 'bg-accent font-medium',
      )}
    >
      <span className="flex flex-1 items-center gap-2">
        {icon} {label}
      </span>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <span
          className="block h-full rounded-full bg-primary transition-[width] duration-500"
          style={{ width: `${(count / Math.max(max, 1)) * 100}%` }}
        />
      </span>
      <span className="w-7 text-right font-mono text-xs text-muted-foreground">{count}</span>
    </button>
  )
}

/** The only sidebar block: browse by category. Short enough to stay on screen without scrolling. */
export function Sidebar() {
  const { stats, filters, setFilter, hotCount } = useDashboard()
  const { saved } = useLibrary()
  const entries = Object.entries(stats?.topic_breakdown ?? {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(...entries.map(([, n]) => n), 1)
  return (
    <aside>
      <BlurFade delay={0.15}>
        <Card>
          <CardHeader>
            <CardTitle className="text-[15px]">Topics</CardTitle>
            <CardDescription>Browse your feed by category.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-0.5">
            <CategoryRow
              label="Hot topics"
              icon={<Flame className="size-4 text-amber-500" aria-hidden />}
              count={hotCount}
              max={Math.max(max, hotCount)}
              active={filters.hot === '1'}
              hint="Stories many outlets are covering right now"
              onClick={() => setFilter({ hot: filters.hot === '1' ? '' : '1', topic: '', saved: '' })}
            />
            <CategoryRow
              label="Saved"
              icon={<Bookmark className="size-4 text-link" aria-hidden />}
              count={saved.length}
              max={Math.max(max, saved.length)}
              active={filters.saved === '1'}
              hint="Articles you saved for later (stored in this browser)"
              onClick={() => setFilter({ saved: filters.saved === '1' ? '' : '1', hot: '', topic: '', cluster: '' })}
            />
            {entries.map(([topic, n]) => (
              <CategoryRow
                key={topic}
                label={topic}
                icon={<span aria-hidden>{TOPIC_EMOJI[topic] ?? '📰'}</span>}
                count={n}
                max={max}
                active={filters.topic === topic}
                onClick={() => setFilter({ topic: filters.topic === topic ? '' : topic, hot: '', saved: '' })}
              />
            ))}
          </CardContent>
        </Card>
      </BlurFade>
    </aside>
  )
}
