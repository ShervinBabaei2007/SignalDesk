// Tests for the smooth chart path helper.
import { describe, expect, it } from 'vitest'
import { monotonePath } from './chart'

describe('monotonePath', () => {
  it('handles empty and single-point input', () => {
    expect(monotonePath([])).toBe('')
    expect(monotonePath([[5, 5]])).toBe('M5,5')
  })

  it('draws one cubic segment per gap, ending on the last point', () => {
    const d = monotonePath([[0, 0], [10, 10], [20, 5]])
    expect(d.startsWith('M0.0,0.0')).toBe(true)
    expect(d.match(/C/g)).toHaveLength(2)
    expect(d.endsWith('20.0,5.0')).toBe(true)
  })

  it('does not overshoot at a peak (all coordinates stay within the data range)', () => {
    const d = monotonePath([[0, 10], [10, 0], [20, 10]])
    const nums = d.replace(/[MC]/g, ' ').trim().split(/[\s,]+/).map(Number)
    const ys = nums.filter((_, i) => i % 2 === 1)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0)
    expect(Math.max(...ys)).toBeLessThanOrEqual(10)
  })
})
