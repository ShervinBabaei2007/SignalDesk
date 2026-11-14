/* The feed query: everything about "which page of the feed am I looking at".
   Pure logic, no React and no fetch of its own: filters in, one normalised
   page out. The data source is passed in, so tests use a fake. */

import { EMPTY_FILTERS, type Article, type ArticlePage, type Filters, type Story, type StoryPage } from '@/lib/api'

export const PAGE_SIZE = 20

/** How many top stories count as "hot". Mirrors HOT_STORIES in backend/app/clustering.py. */
export const HOT_STORIES = 8

/** What the server is asked for: the filters, a page, grouped or flat, and saved ids. */
export interface FeedQuery {
  filters: Filters
  page: number
  grouped: boolean
  /** Comma-separated saved ids when the Saved category is selected ('0' = none). */
  ids?: string
}

/** One page of the feed. Stories in grouped mode, articles in flat mode, never both. */
export interface FeedPage {
  stories: Story[]
  articles: Article[]
  /** Pages are counted in stories when grouped, in articles otherwise. */
  total: number
  articleTotal: number
}

export interface FeedSource {
  stories: (filters: Filters, offset: number, limit: number, ids?: string) => Promise<StoryPage>
  articles: (filters: Filters, offset: number, limit: number, ids?: string) => Promise<ArticlePage>
}

/** The server reads '0' as "no ids", so an empty saved list shows an empty feed instead of everything. */
export function savedIdsParam(saved: number[]): string {
  return saved.join(',') || '0'
}

export function hasActiveFilters(f: Filters): boolean {
  return !!(f.search || f.source || f.topic || f.sentiment || f.cluster || f.hot || f.saved)
}

/** Every filter off; the chosen sort order stays. */
export function clearedFilters(f: Filters): Filters {
  return { ...EMPTY_FILTERS, order: f.order }
}

/** Show every report of one story: other filters are cleared so none of them hide it. */
export function storyFilters(f: Filters, clusterId: number): Filters {
  return { ...clearedFilters(f), cluster: String(clusterId) }
}

export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE))
}

export async function loadFeedPage(source: FeedSource, q: FeedQuery): Promise<FeedPage> {
  const offset = (q.page - 1) * PAGE_SIZE
  if (q.grouped) {
    const res = await source.stories(q.filters, offset, PAGE_SIZE, q.ids)
    return { stories: res.items, articles: [], total: res.total, articleTotal: res.article_total }
  }
  const res = await source.articles(q.filters, offset, PAGE_SIZE, q.ids)
  return { stories: [], articles: res.items, total: res.total, articleTotal: res.total }
}

/** Latest-wins gate: only the most recent request may apply its result. */
export function latestOnly() {
  let current = 0
  return {
    begin(): () => boolean {
      const mine = ++current
      return () => mine === current
    },
  }
}
