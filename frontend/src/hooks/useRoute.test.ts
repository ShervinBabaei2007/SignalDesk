// Tests for turning URL hashes into routes.
import { describe, expect, it } from 'vitest'
import { parseRoute } from '@/hooks/useRoute'

describe('parseRoute', () => {
  it('sends first-time visitors with no hash to the landing page', () => {
    expect(parseRoute('', false)).toEqual({ name: 'landing' })
    expect(parseRoute('#/', false)).toEqual({ name: 'landing' })
  })

  it('sends returning visitors straight to the dashboard', () => {
    expect(parseRoute('', true)).toEqual({ name: 'home' })
  })

  it('always shows the landing page at #/welcome', () => {
    expect(parseRoute('#/welcome', true)).toEqual({ name: 'landing' })
  })

  it('keeps deep links to articles and stories working for first-time visitors', () => {
    expect(parseRoute('#/article/7', false)).toEqual({ name: 'article', id: 7 })
    expect(parseRoute('#/story/3', false)).toEqual({ name: 'story', id: 3 })
  })
})
