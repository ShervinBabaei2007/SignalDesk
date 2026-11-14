import { describe, expect, it } from 'vitest'
import { addRead, MAX_READ, parseIds, toggleId } from './library'

describe('parseIds', () => {
  it('reads a stored list and drops anything that is not a positive integer', () => {
    expect(parseIds('[3, 1, 2]')).toEqual([3, 1, 2])
    expect(parseIds('[1, "2", 1.5, -4, null, 1, 7]')).toEqual([1, 7])
  })

  it('survives missing or corrupt storage', () => {
    expect(parseIds(null)).toEqual([])
    expect(parseIds('')).toEqual([])
    expect(parseIds('not json')).toEqual([])
    expect(parseIds('{"a": 1}')).toEqual([])
  })
})

describe('toggleId', () => {
  it('adds new ids at the front and removes existing ones', () => {
    expect(toggleId([2, 3], 1)).toEqual([1, 2, 3])
    expect(toggleId([1, 2, 3], 2)).toEqual([1, 3])
    expect(toggleId([], 5)).toEqual([5])
  })
})

describe('addRead', () => {
  it('moves a re-read article to the front without duplicating it', () => {
    expect(addRead([1, 2, 3], 3)).toEqual([3, 1, 2])
    expect(addRead([1, 2, 3], 1)).toEqual([1, 2, 3])
  })

  it('keeps the list bounded', () => {
    const many = Array.from({ length: MAX_READ }, (_, i) => i + 1)
    const next = addRead(many, 99999)
    expect(next).toHaveLength(MAX_READ)
    expect(next[0]).toBe(99999)
  })
})
