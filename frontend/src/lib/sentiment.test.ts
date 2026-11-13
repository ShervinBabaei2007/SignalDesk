import { describe, expect, it } from 'vitest'
import { describeAverage, describeSentiment, formatScore, scalePosition } from './sentiment'

describe('describeSentiment', () => {
  it.each([
    [0.9, 'Very positive', 'positive'],
    [0.5, 'Very positive', 'positive'],
    [0.3, 'Positive', 'positive'],
    [0.15, 'Neutral', 'neutral'],
    [0, 'Neutral', 'neutral'],
    [-0.15, 'Neutral', 'neutral'],
    [-0.3, 'Negative', 'negative'],
    [-0.5, 'Very negative', 'negative'],
    [-1, 'Very negative', 'negative'],
  ])('score %d reads as %s', (score, label, tone) => {
    const d = describeSentiment(score)
    expect(d.label).toBe(label)
    expect(d.tone).toBe(tone)
  })

  it('always explains the level in plain words', () => {
    expect(describeSentiment(0.7).blurb).toMatch(/positive words/)
    expect(describeSentiment(-0.7).blurb).toMatch(/negative words/)
  })
})

describe('formatting helpers', () => {
  it('shows an explicit sign and a true minus', () => {
    expect(formatScore(0.5)).toBe('+0.50')
    expect(formatScore(-0.11)).toBe('−0.11')
    expect(formatScore(0)).toBe('+0.00')
  })

  it('describes averages without jargon', () => {
    expect(describeAverage(-0.11)).toBe('Mixed or neutral')
    expect(describeAverage(0.3)).toBe('Mostly positive')
  })

  it('places scores on a 0-100 scale for gauges', () => {
    expect(scalePosition(-1)).toBe(0)
    expect(scalePosition(0)).toBe(50)
    expect(scalePosition(1)).toBe(100)
    expect(scalePosition(5)).toBe(100)
  })
})
