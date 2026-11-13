import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  api, ApiError, EMPTY_FILTERS,
  type Article, type Digest, type Feed, type Filters, type Health, type Stats, type TrendingStory,
} from '@/lib/api'

export const PAGE_SIZE = 20

interface DashboardValue {
  filters: Filters
  setFilter: (patch: Partial<Filters>) => void
  clearFilters: () => void
  /** Show every report of one story, clearing other filters so none of them hide it. */
  openStory: (clusterId: number) => void
  hasActiveFilters: boolean
  /** Articles that belong to the hot stories (matches the `hot` feed filter). */
  hotCount: number
  articles: Article[]
  total: number
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

interface Query {
  filters: Filters
  page: number
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [page, setPageState] = useState(1)
  const [applied, setApplied] = useState<Query>({ filters: EMPTY_FILTERS, page: 1 })
  const [articles, setArticles] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<Stats | null>(null)
  const [digest, setDigest] = useState<Digest | null>(null)
  const [trending, setTrending] = useState<TrendingStory[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState('')
  const requestId = useRef(0)

  const loadArticles = useCallback(async (q: Query) => {
    const id = ++requestId.current
    setLoading(true)
    try {
      const res = await api.articles(q.filters, (q.page - 1) * PAGE_SIZE, PAGE_SIZE)
      if (id !== requestId.current) return // a newer request superseded this one
      setArticles(res.items)
      setTotal(res.total)
    } catch (err) {
      toast.error(`Failed to load articles: ${(err as Error).message}`)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [])

  const loadSide = useCallback(async () => {
    const [s, d, t, h, fs] = await Promise.allSettled([
      api.stats(), api.digest(), api.trending(8), api.health(), api.feeds(),
    ])
    if (s.status === 'fulfilled') setStats(s.value)
    if (d.status === 'fulfilled') setDigest(d.value)
    if (t.status === 'fulfilled') setTrending(t.value)
    if (h.status === 'fulfilled') setHealth(h.value)
    if (fs.status === 'fulfilled') setFeeds(fs.value)
  }, [])

  // Typing in search is debounced; filter changes and page clicks apply immediately.
  useEffect(() => {
    const searchChanged = filters.search !== applied.filters.search
    const t = setTimeout(() => setApplied({ filters, page }), searchChanged ? 250 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `applied` is only read to detect a search change
  }, [filters, page])

  useEffect(() => {
    void loadArticles(applied)
  }, [applied, loadArticles])

  useEffect(() => {
    void loadSide()
  }, [loadSide])

  const setFilter = useCallback((patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }))
    setPageState(1)
  }, [])
  const clearFilters = useCallback(() => {
    setFilters((f) => ({ ...EMPTY_FILTERS, order: f.order }))
    setPageState(1)
  }, [])
  const openStory = useCallback((clusterId: number) => {
    setFilters((f) => ({ ...EMPTY_FILTERS, order: f.order, cluster: String(clusterId) }))
    setPageState(1)
  }, [])

  const refreshAll = useCallback(async () => {
    await Promise.all([loadArticles(applied), loadSide()])
  }, [applied, loadArticles, loadSide])

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
      await refreshAll()
    } catch (err) {
      const e = err as ApiError
      setIngestResult(e.message)
      toast.error(e.status === 429 ? 'Just checked — give the feeds a moment' : `Ingestion failed: ${e.message}`)
    } finally {
      setIngesting(false)
    }
  }, [refreshAll])

  const hasActiveFilters = !!(filters.search || filters.source || filters.topic || filters.sentiment || filters.cluster || filters.hot)
  const sources = useMemo(() => feeds.map((f) => f.name).sort(), [feeds])
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hotCount = trending.reduce((n, t) => n + t.reports, 0)

  const value: DashboardValue = {
    filters, setFilter, clearFilters, openStory, hasActiveFilters, hotCount, articles, total, page, pageCount,
    setPage: setPageState, loading, stats, digest, trending, health, sources, feeds, refreshFeeds, refreshAll,
    ingesting, ingestResult, runIngest,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDashboard(): DashboardValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDashboard must be used inside DashboardProvider')
  return v
}
