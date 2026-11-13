import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api, ApiError, EMPTY_FILTERS, type Article, type Digest, type Feed, type Filters, type Health, type Stats } from '@/lib/api'

const PAGE = 25

interface DashboardValue {
  filters: Filters
  setFilter: (patch: Partial<Filters>) => void
  clearFilters: () => void
  hasActiveFilters: boolean
  articles: Article[]
  total: number
  loading: boolean
  loadingMore: boolean
  loadMore: () => void
  stats: Stats | null
  digest: Digest | null
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
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [articles, setArticles] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [digest, setDigest] = useState<Digest | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState('')
  const requestId = useRef(0)

  const loadArticles = useCallback(async (f: Filters) => {
    const id = ++requestId.current
    setLoading(true)
    try {
      const page = await api.articles(f, 0, PAGE)
      if (id !== requestId.current) return // a newer filter change superseded this request
      setArticles(page.items)
      setTotal(page.total)
    } catch (err) {
      toast.error(`Failed to load articles: ${(err as Error).message}`)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [])

  const loadSide = useCallback(async () => {
    const [s, d, h, fs] = await Promise.allSettled([api.stats(), api.digest(), api.health(), api.feeds()])
    if (s.status === 'fulfilled') setStats(s.value)
    if (d.status === 'fulfilled') setDigest(d.value)
    if (h.status === 'fulfilled') setHealth(h.value)
    if (fs.status === 'fulfilled') setFeeds(fs.value)
  }, [])

  // Debounce typing in search; every other filter applies immediately.
  const firstRun = useRef(true)
  useEffect(() => {
    const delay = firstRun.current ? 0 : 250
    firstRun.current = false
    const t = setTimeout(() => void loadArticles(filters), delay)
    return () => clearTimeout(t)
  }, [filters, loadArticles])

  useEffect(() => {
    void loadSide()
  }, [loadSide])

  const setFilter = useCallback((patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch })), [])
  const clearFilters = useCallback(() => setFilters((f) => ({ ...EMPTY_FILTERS, order: f.order })), [])

  const loadMore = useCallback(async () => {
    setLoadingMore(true)
    try {
      const page = await api.articles(filters, articles.length, PAGE)
      setArticles((prev) => [...prev, ...page.items])
      setTotal(page.total)
    } catch (err) {
      toast.error(`Failed to load more: ${(err as Error).message}`)
    } finally {
      setLoadingMore(false)
    }
  }, [filters, articles.length])

  const refreshAll = useCallback(async () => {
    await Promise.all([loadArticles(filters), loadSide()])
  }, [filters, loadArticles, loadSide])

  const refreshFeeds = useCallback(async () => {
    setFeeds(await api.feeds())
  }, [])

  const runIngest = useCallback(async () => {
    setIngesting(true)
    setIngestResult('Fetching feeds, removing duplicates and analyzing…')
    try {
      const r = await api.ingest()
      setIngestResult(
        `${r.added} new · ${r.fetched} fetched · ${r.skipped} duplicates skipped · ${r.duration_seconds}s`,
      )
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

  const hasActiveFilters = !!(filters.search || filters.source || filters.topic || filters.sentiment || filters.cluster)
  const sources = useMemo(() => feeds.map((f) => f.name).sort(), [feeds])

  const value: DashboardValue = {
    filters, setFilter, clearFilters, hasActiveFilters, articles, total, loading, loadingMore,
    loadMore: () => void loadMore(), stats, digest, health, sources, feeds, refreshFeeds, refreshAll,
    ingesting, ingestResult, runIngest,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDashboard(): DashboardValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDashboard must be used inside DashboardProvider')
  return v
}
