import { createContext, useCallback, useContext, type ReactNode } from 'react'
import { useLibrary } from '@/hooks/useLibrary'
import { useFeedQuery } from '@/hooks/useFeedQuery'
import { useIngest } from '@/hooks/useIngest'
import { useSettings } from '@/hooks/useSettings'
import { useSideData } from '@/hooks/useSideData'
import type { Article, Digest, Story, Feed, Filters, Health, Stats, TrendingStory } from '@/lib/api'

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
  const { reload, ...feed } = useFeedQuery(grouped, saved)
  const { reloadSide, ...side } = useSideData()
  const refreshAll = useCallback(async () => {
    await Promise.all([reload(), reloadSide()])
  }, [reload, reloadSide])
  const ingest = useIngest(refreshAll)

  const value: DashboardValue = { ...feed, ...side, ...ingest, grouped, refreshAll }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDashboard(): DashboardValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDashboard must be used inside DashboardProvider')
  return v
}
