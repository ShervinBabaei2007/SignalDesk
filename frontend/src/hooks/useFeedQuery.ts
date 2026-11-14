// Hook that loads the feed page for the current filters and page.
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, EMPTY_FILTERS, type Filters } from '@/lib/api'
import {
  clearedFilters, hasActiveFilters, latestOnly, loadFeedPage, pageCount, savedIdsParam, storyFilters,
  type FeedPage, type FeedQuery,
} from '@/lib/feedQuery'

/** Feed page used before the first load. */
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

  /** Fetch one feed page, letting only the newest request update the view. */
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

  // Turn the UI state into the query to send, waiting for a pause in search typing first.
  useEffect(() => {
    const searchChanged = filters.search !== appliedSearch.current
    const t = setTimeout(() => {
      appliedSearch.current = filters.search
      // Saved ids are sent only while the Saved category is selected.
      setApplied({ filters, page, grouped, ids: filters.saved ? savedKey : undefined })
    }, searchChanged ? 250 : 0) // 250 ms debounce for typing; other changes apply on the next tick
    return () => clearTimeout(t)
  }, [filters, page, grouped, savedKey])

  // Fetch whenever the applied query changes.
  useEffect(() => {
    void load(applied)
  }, [applied, load])

  /** Change some filters and go back to the first page. */
  const setFilter = useCallback((patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }))
    setPageState(1)
  }, [])
  /** Turn every filter off (keeping the sort order) and go back to the first page. */
  const clearFilters = useCallback(() => {
    setFilters(clearedFilters)
    setPageState(1)
  }, [])
  /** Show every report of one story from the first page. */
  const openStory = useCallback((clusterId: number) => {
    setFilters((f) => storyFilters(f, clusterId))
    setPageState(1)
  }, [])
  /** Fetch the current page again without changing the query. */
  const reload = useCallback(() => load(applied), [applied, load])

  return {
    filters, setFilter, clearFilters, openStory, page, setPage: setPageState,
    hasActiveFilters: hasActiveFilters(filters),
    stories: feed.stories, articles: feed.articles, total: feed.total, articleTotal: feed.articleTotal,
    pageCount: pageCount(feed.total), loading, reload,
  }
}
