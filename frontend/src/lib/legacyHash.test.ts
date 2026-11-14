import { describe, expect, it } from 'vitest'
import { legacyHashPath } from '@/lib/legacyHash'

describe('legacyHashPath', () => {
  it('maps old article and story hash links to real paths', () => {
    expect(legacyHashPath('#/article/7')).toBe('/article/7')
    expect(legacyHashPath('#/story/3')).toBe('/story/3')
  })

  it('maps the old welcome hash', () => {
    expect(legacyHashPath('#/welcome')).toBe('/welcome')
  })

  it('ignores anything else', () => {
    expect(legacyHashPath('')).toBeNull()
    expect(legacyHashPath('#/')).toBeNull()
    expect(legacyHashPath('#/article/abc')).toBeNull()
  })
})
