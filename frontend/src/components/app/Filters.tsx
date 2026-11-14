import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDashboard } from '@/hooks/useDashboard'
import type { Filters as FilterState } from '@/lib/api'
import { TOPIC_EMOJI } from '@/lib/format'

const ALL = 'all'

function FilterSelect({
  label, value, onChange, options, className,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  className?: string
}) {
  return (
    <Select items={options} value={value || ALL} onValueChange={(v) => onChange(v === ALL || v === null ? '' : String(v))}>
      <SelectTrigger aria-label={label} className={className ?? 'w-full'}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false}>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function Filters() {
  const { filters, setFilter, sources, stats } = useDashboard()
  const topics = Object.keys(stats?.topic_breakdown ?? {}).sort()
  const set = <K extends keyof FilterState>(key: K) => (v: string) => setFilter({ [key]: v } as Partial<FilterState>)

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))]">
      <div className="relative col-span-2 md:col-span-4 xl:col-span-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          type="search"
          aria-label="Search articles"
          placeholder="Search articles…"
          value={filters.search}
          onChange={(e) => setFilter({ search: e.target.value })}
          className="h-9 pl-8"
        />
      </div>
      <FilterSelect
        label="Source"
        value={filters.source}
        onChange={set('source')}
        options={[{ value: ALL, label: 'All sources' }, ...sources.map((s) => ({ value: s, label: s }))]}
      />
      <FilterSelect
        label="Topic"
        value={filters.saved ? 'saved' : filters.hot ? 'hot' : filters.topic}
        onChange={(v) =>
          setFilter(
            v === 'hot' ? { hot: '1', topic: '', saved: '' } : v === 'saved' ? { saved: '1', topic: '', hot: '' } : { topic: v, hot: '', saved: '' },
          )
        }
        options={[{ value: ALL, label: 'All topics' }, { value: 'hot', label: '🔥 Hot topics' }, { value: 'saved', label: '🔖 Saved' }, ...topics.map((t) => ({ value: t, label: `${TOPIC_EMOJI[t] ?? '📰'} ${t}` }))]}
      />
      <FilterSelect
        label="Sentiment"
        value={filters.sentiment}
        onChange={set('sentiment')}
        options={[
          { value: ALL, label: 'Any sentiment' },
          { value: 'positive', label: 'Positive' },
          { value: 'neutral', label: 'Neutral' },
          { value: 'negative', label: 'Negative' },
        ]}
      />
      <FilterSelect
        label="Sort order"
        value={filters.order}
        onChange={(v) => setFilter({ order: v || 'newest' })}
        options={[
          { value: 'newest', label: 'Newest first' },
          { value: 'info', label: 'Most informative' },
          { value: 'oldest', label: 'Oldest first' },
          { value: 'sentiment_high', label: 'Most positive' },
          { value: 'sentiment_low', label: 'Most negative' },
        ]}
      />
    </div>
  )
}
