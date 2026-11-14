import { describe, expect, it } from 'vitest'
import type { Digest } from '@/lib/api'
import { briefFilename, digestText } from '@/lib/brief'

const item = { id: 1, title: 'Chip plant opens', source: 'Wire', sentiment: 0.4, topic: 'Tech', url: 'https://x.test/1' }

const digest: Digest = {
  generated_at: '2026-11-14T18:30:00',
  articles_last_24h: 12,
  avg_sentiment: -0.05,
  headline: 'Markets steady as chip news lifts tech.',
  topic_breakdown: { Tech: 5, Business: 4, World: 3, Sport: 2, Health: 1, Science: 1 },
  top_positive: [item],
  top_negative: [{ ...item, id: 2, title: 'Plant closes', sentiment: -0.6 }],
}

describe('digestText', () => {
  it('renders the same sections as the emailed brief', () => {
    const text = digestText(digest)
    expect(text).toContain('☀️ SignalDesk Daily Brief — Nov 14, 2026')
    expect(text).toContain('Signals: 12 · Avg sentiment: -0.05')
    expect(text).toContain('• +0.40 · Chip plant opens (Wire) — https://x.test/1')
    expect(text).toContain('• -0.60 · Plant closes (Wire) — https://x.test/1')
    expect(text.endsWith('— SignalDesk')).toBe(true)
  })

  it('lists only the five largest topics', () => {
    expect(digestText(digest)).toContain('Topics: Tech 5 · Business 4 · World 3 · Sport 2 · Health 1\n')
  })

  it('leaves out empty sections', () => {
    const text = digestText({ ...digest, topic_breakdown: {}, top_positive: [], top_negative: [] })
    expect(text).not.toMatch(/Topics:|Most positive|Most negative/)
  })
})

describe('briefFilename', () => {
  it('uses the UTC date of the brief', () => {
    expect(briefFilename(digest)).toBe('signaldesk-brief-2026-11-14.txt')
  })
})
