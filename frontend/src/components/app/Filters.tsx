// Search box and topic, source, sentiment and sort selects that drive the feed.
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDashboard } from '@/hooks/useDashboard'
import type { Filters as FilterState } from '@/lib/api'
import { TOPIC_EMOJI } from '@/lib/format'

/** Select value meaning no filter. */
const ALL = 'all'

/** The Topic select also holds the Hot and Saved categories; picking one clears the other two. */
function topicPatch(value: string): Partial<FilterState> {
  if (value === 'hot') return { hot: '1', topic: '', saved: '' }
  if (value === 'saved') return { saved: '1', topic: '', hot: '' }
  return { topic: value, hot: '', saved: '' }
}

/** Current value of the combined topic/hot/saved select. */
function topicValue(filters: FilterState): string {
  if (filters.saved) return 'saved'
  if (filters.hot) return 'hot'
  return filters.topic
}

/** A labelled select used by the filter bar. */
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
    // An empty filter shows as "all", and picking "all" (or clearing) sends back an empty filter.
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

/** The bar above the feed for searching, filtering and sorting articles. */
export function Filters() {
  const { filters, setFilter, sources, stats } = useDashboard()
  const topics = Object.keys(stats?.topic_breakdown ?? {}).sort()
  // Builds an onChange handler that writes the picked value into one filter field.
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
        value={topicValue(filters)}
        onChange={(v) => setFilter(topicPatch(v))}
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
