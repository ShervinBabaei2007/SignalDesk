// Tests for feed paging, filter resets and stale-request handling.
import { describe, expect, it } from 'vitest'
import { EMPTY_FILTERS, feedParams, type ArticlePage, type StoryPage } from '@/lib/api'
import {
  PAGE_SIZE, clearedFilters, hasActiveFilters, latestOnly, loadFeedPage, pageCount, savedIdsParam, storyFilters,
  type FeedSource,
} from '@/lib/feedQuery'

/** A fake feed source that records requests and returns fixed pages. */
function fakeSource() {
  const calls: { kind: string; offset: number; limit: number; ids?: string }[] = []
  const source: FeedSource = {
    stories: async (_f, offset, limit, ids) => {
      calls.push({ kind: 'stories', offset, limit, ids })
      return { items: [{ key: 'c1' }], total: 7, article_total: 19, offset, limit } as unknown as StoryPage
    },
    articles: async (_f, offset, limit, ids) => {
      calls.push({ kind: 'articles', offset, limit, ids })
      return { items: [{ id: 1 }, { id: 2 }], total: 42, offset, limit } as unknown as ArticlePage
    },
  }
  return { source, calls }
}

describe('loadFeedPage', () => {
  it('grouped mode asks for stories and leaves articles empty', async () => {
    const { source, calls } = fakeSource()
    const page = await loadFeedPage(source, { filters: EMPTY_FILTERS, page: 3, grouped: true })
    expect(calls).toEqual([{ kind: 'stories', offset: 2 * PAGE_SIZE, limit: PAGE_SIZE, ids: undefined }])
    expect(page.stories).toHaveLength(1)
    expect(page.articles).toEqual([])
    expect(page).toMatchObject({ total: 7, articleTotal: 19 })
  })

  it('flat mode asks for articles, and the article total equals the total', async () => {
    const { source } = fakeSource()
    const page = await loadFeedPage(source, { filters: EMPTY_FILTERS, page: 1, grouped: false, ids: '4,5' })
    expect(page.stories).toEqual([])
    expect(page.articles).toHaveLength(2)
    expect(page).toMatchObject({ total: 42, articleTotal: 42 })
  })
})

describe('saved ids', () => {
  it("sends '0' for an empty saved list so the feed is empty rather than unfiltered", () => {
    expect(savedIdsParam([])).toBe('0')
    expect(savedIdsParam([3, 9])).toBe('3,9')
  })

  it('reaches the query string as ids, and the saved flag itself is never sent', () => {
    const params = feedParams({ ...EMPTY_FILTERS, saved: '1' }, 0, 20, savedIdsParam([]))
    expect(params.get('ids')).toBe('0')
    expect(params.has('saved')).toBe(false)
  })
})

describe('filter resets', () => {
  const busy = { ...EMPTY_FILTERS, search: 'oil', topic: 'Business', hot: '1', order: 'info' }

  it('clearing keeps only the sort order', () => {
    expect(clearedFilters(busy)).toEqual({ ...EMPTY_FILTERS, order: 'info' })
    expect(hasActiveFilters(clearedFilters(busy))).toBe(false)
  })

  it('opening a story drops every other filter so none can hide it', () => {
    const f = storyFilters(busy, 12)
    expect(f).toEqual({ ...EMPTY_FILTERS, order: 'info', cluster: '12' })
    expect(hasActiveFilters(f)).toBe(true)
  })

  it('a sort order alone is not an active filter', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, order: 'oldest' })).toBe(false)
  })
})

describe('pageCount', () => {
  it('is at least one page, and rounds up', () => {
    expect(pageCount(0)).toBe(1)
    expect(pageCount(PAGE_SIZE)).toBe(1)
    expect(pageCount(PAGE_SIZE + 1)).toBe(2)
  })
})

describe('latestOnly', () => {
  it('lets only the newest request apply its result', () => {
    const gate = latestOnly()
    const first = gate.begin()
    const second = gate.begin()
    expect(first()).toBe(false)
    expect(second()).toBe(true)
  })
})
