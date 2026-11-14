// Dashboard context combining filters, the feed, side data and ingest into one value.
import { createContext, useCallback, useContext, type ReactNode } from 'react'
import { useFeedQuery } from '@/hooks/useFeedQuery'
import { useIngest } from '@/hooks/useIngest'
import { useLibrary } from '@/hooks/useLibrary'
import { useSettings } from '@/hooks/useSettings'
import { useSideData } from '@/hooks/useSideData'
import type { Article, Digest, Feed, Filters, Health, Stats, Story, TrendingStory } from '@/lib/api'

export { PAGE_SIZE } from '@/lib/feedQuery'

/** Everything the dashboard components read and call. */
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

/** Context holding the dashboard value. */
const Ctx = createContext<DashboardValue | null>(null)

/** Provides dashboard state to the app. */
export function DashboardProvider({ children }: { children: ReactNode }) {
  const { grouped } = useSettings()
  const { saved } = useLibrary()
  const { reload, ...feed } = useFeedQuery(grouped, saved)
  const { reloadSide, ...side } = useSideData()
  /** Reload the feed page and the side panels together, e.g. after an ingest. */
  const refreshAll = useCallback(async () => {
    await Promise.all([reload(), reloadSide()])
  }, [reload, reloadSide])
  const ingest = useIngest(refreshAll)

  const value: DashboardValue = { ...feed, ...side, ...ingest, grouped, refreshAll }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** Read the dashboard state; must be used inside DashboardProvider. */
export function useDashboard(): DashboardValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDashboard must be used inside DashboardProvider')
  return v
}
