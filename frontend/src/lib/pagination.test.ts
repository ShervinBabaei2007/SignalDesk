// Tests for the page-number window.
import { describe, expect, it } from 'vitest'
import { pageWindow } from './pagination'

describe('pageWindow', () => {
  it('shows every page when there are few', () => {
    expect(pageWindow(1, 1)).toEqual([1])
    expect(pageWindow(2, 5)).toEqual([1, 2, 3, 4, 5])
  })

  it('collapses far pages into gaps around the current page', () => {
    expect(pageWindow(1, 20)).toEqual([1, 2, 'gap', 20])
    expect(pageWindow(10, 20)).toEqual([1, 'gap', 9, 10, 11, 'gap', 20])
    expect(pageWindow(20, 20)).toEqual([1, 'gap', 19, 20])
  })

  it('fills a single skipped page instead of showing an ellipsis', () => {
    expect(pageWindow(4, 8)).toEqual([1, 2, 3, 4, 5, 'gap', 8])
  })

  it('returns nothing when there are no pages', () => {
    expect(pageWindow(1, 0)).toEqual([])
  })
})
