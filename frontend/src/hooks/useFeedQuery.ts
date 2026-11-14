import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, EMPTY_FILTERS, type Filters } from '@/lib/api'
import {
  clearedFilters, hasActiveFilters, latestOnly, loadFeedPage, pageCount, savedIdsParam, storyFilters,
  type FeedPage, type FeedQuery,
} from '@/lib/feedQuery'

const EMPTY_PAGE: FeedPage = { stories: [], articles: [], total: 0, articleTotal: 0 }

/** Filters, paging and the loaded feed page. Search typing is debounced; everything else applies at once. */
export function useFeedQuery(grouped: boolean, saved: number[]) {
  const savedKey = savedIdsParam(saved)
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [page, setPageState] = useState(1)
  const [applied, setApplied] = useState<FeedQuery>({ filters: EMPTY_FILTERS, page: 1, grouped })
  const [feed, setFeed] = useState<FeedPage>(EMPTY_PAGE)
  const [loading, setLoading] = useState(true)
  const gate = useRef(latestOnly())
  // The search text last sent to the server; typing differs from it and is debounced, other changes are not.
  const appliedSearch = useRef(applied.filters.search)

  const load = useCallback(async (q: FeedQuery) => {
    const isLatest = gate.current.begin()
    setLoading(true)
    try {
      const result = await loadFeedPage(api, q)
      if (isLatest()) setFeed(result)
    } catch (err) {
      toast.error(`Failed to load articles: ${(err as Error).message}`)
    } finally {
      if (isLatest()) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const searchChanged = filters.search !== appliedSearch.current
    const t = setTimeout(() => {
      appliedSearch.current = filters.search
      setApplied({ filters, page, grouped, ids: filters.saved ? savedKey : undefined })
    }, searchChanged ? 250 : 0)
    return () => clearTimeout(t)
  }, [filters, page, grouped, savedKey])

  useEffect(() => {
    void load(applied)
  }, [applied, load])

  const setFilter = useCallback((patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }))
    setPageState(1)
  }, [])
  const clearFilters = useCallback(() => {
    setFilters(clearedFilters)
    setPageState(1)
  }, [])
  const openStory = useCallback((clusterId: number) => {
    setFilters((f) => storyFilters(f, clusterId))
    setPageState(1)
  }, [])
  const reload = useCallback(() => load(applied), [applied, load])

  return {
    filters, setFilter, clearFilters, openStory, page, setPage: setPageState,
    hasActiveFilters: hasActiveFilters(filters),
    stories: feed.stories, articles: feed.articles, total: feed.total, articleTotal: feed.articleTotal,
    pageCount: pageCount(feed.total), loading, reload,
  }
}
