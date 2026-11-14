// Tests for the information-score levels.
import { describe, expect, it } from 'vitest'
import { infoLevel } from './info'

describe('infoLevel', () => {
  it.each([
    [100, 'Very detailed'],
    [75, 'Very detailed'],
    [74.4, 'Detailed'],
    [50, 'Detailed'],
    [49, 'Brief'],
    [25, 'Brief'],
    [24, 'Thin'],
    [0, 'Thin'],
  ])('score %d reads as %s', (score, label) => {
    expect(infoLevel(score).label).toBe(label)
  })

  it('treats a missing score as thin and rounds the value', () => {
    expect(infoLevel(null).label).toBe('Thin')
    expect(infoLevel(undefined).value).toBe(0)
    expect(infoLevel(81.6).value).toBe(82)
  })
})
