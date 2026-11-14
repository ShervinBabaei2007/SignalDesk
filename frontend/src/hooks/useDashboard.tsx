import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { useLibrary } from '@/hooks/useLibrary'
import { useFeedQuery } from '@/hooks/useFeedQuery'
import { useSettings } from '@/hooks/useSettings'
import {
  api, ApiError,
  type Article, type Digest, type Story, type Feed, type Filters, type Health, type Stats, type TrendingStory,
} from '@/lib/api'
import { HOT_STORIES } from '@/lib/feedQuery'

export { PAGE_SIZE } from '@/lib/feedQuery'

interface DashboardValue {
  filters: Filters
  setFilter: (patch: Partial<Filters>) => void
  clearFilters: () => void
  /** Show every report of one story, clearing other filters so none of them hide it. */
  openStory: (clusterId: number) => void
  hasActiveFilters: boolean
  /** Articles that belong to the hot stories (matches the `hot` feed filter). */
  hotCount: number
  /** Grouped mode: one entry per event. Empty in flat mode. */
  stories: Story[]
  /** Flat mode: one entry per report. Empty in grouped mode. */
  articles: Article[]
  grouped: boolean
  /** Pages are counted in stories when grouped, in articles otherwise. */
  total: number
  articleTotal: number
  page: number
  pageCount: number
  setPage: (page: number) => void
  loading: boolean
  stats: Stats | null
  digest: Digest | null
  trending: TrendingStory[]
  health: Health | null
  sources: string[]
  feeds: Feed[]
  refreshFeeds: () => Promise<void>
  refreshAll: () => Promise<void>
  ingesting: boolean
  ingestResult: string
  runIngest: () => Promise<void>
}

const Ctx = createContext<DashboardValue | null>(null)

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { grouped } = useSettings()
  const { saved } = useLibrary()
  const feed = useFeedQuery(grouped, saved)
  const [stats, setStats] = useState<Stats | null>(null)
  const [digest, setDigest] = useState<Digest | null>(null)
  const [trending, setTrending] = useState<TrendingStory[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState('')

  const loadSide = useCallback(async () => {
    const [s, d, t, h, fs] = await Promise.allSettled([
      api.stats(), api.digest(), api.trending(HOT_STORIES), api.health(), api.feeds(),
    ])
    if (s.status === 'fulfilled') setStats(s.value)
    if (d.status === 'fulfilled') setDigest(d.value)
    if (t.status === 'fulfilled') setTrending(t.value)
    if (h.status === 'fulfilled') setHealth(h.value)
    if (fs.status === 'fulfilled') setFeeds(fs.value)
  }, [])

  useEffect(() => {
    void loadSide()
  }, [loadSide])

  const { reload } = feed
  const refreshAll = useCallback(async () => {
    await Promise.all([reload(), loadSide()])
  }, [reload, loadSide])

  const refreshFeeds = useCallback(async () => {
    setFeeds(await api.feeds())
  }, [])

  const runIngest = useCallback(async () => {
    setIngesting(true)
    setIngestResult('Fetching feeds, removing duplicates and analyzing…')
    try {
      const r = await api.ingest()
      setIngestResult(`${r.added} new · ${r.fetched} fetched · ${r.skipped} duplicates skipped · ${r.duration_seconds}s`)
      toast.success(
        r.added ? `${r.added} new article${r.added === 1 ? '' : 's'} added` : 'All caught up — no new articles right now',
      )
      if (r.alerts?.length) {
        const first = r.alerts[0]
        toast(`🔔 ${r.alerts.length} watched ${r.alerts.length === 1 ? 'story' : 'stories'} matched`, {
          description: r.alerts.slice(0, 3).map((a) => `“${a.term}”: ${a.title}`).join('\n'),
          duration: 10000,
          action: {
            label: 'Open',
            onClick: () => {
              location.hash = first.cluster_id ? `#/story/${first.cluster_id}` : `#/article/${first.article_id}`
            },
          },
        })
      }
      await refreshAll()
    } catch (err) {
      const e = err as ApiError
      setIngestResult(e.message)
      toast.error(e.status === 429 ? 'Just checked — give the feeds a moment' : `Ingestion failed: ${e.message}`)
    } finally {
      setIngesting(false)
    }
  }, [refreshAll])

  const sources = useMemo(() => feeds.map((f) => f.name).sort(), [feeds])
  const hotCount = trending.reduce((n, t) => n + t.reports, 0)

  const value: DashboardValue = {
    filters: feed.filters, setFilter: feed.setFilter, clearFilters: feed.clearFilters, openStory: feed.openStory,
    hasActiveFilters: feed.hasActiveFilters, hotCount, stories: feed.stories, articles: feed.articles, grouped,
    total: feed.total, articleTotal: feed.articleTotal, page: feed.page, pageCount: feed.pageCount,
    setPage: feed.setPage, loading: feed.loading, stats, digest, trending, health, sources, feeds, refreshFeeds, refreshAll,
    ingesting, ingestResult, runIngest,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDashboard(): DashboardValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDashboard must be used inside DashboardProvider')
  return v
}
