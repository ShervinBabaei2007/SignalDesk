// Tests for the claims, timeline, sources and pipeline helpers, and the API methods behind them.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { barHeights, dayLabel, fillSeries, formatDuration, minutesAgo, percent, reliabilityTone, STALE_AFTER_MINUTES } from '@/lib/insights'

afterEach(() => vi.unstubAllGlobals())

/** Replace fetch with a stub that answers 200 with `body`; returns the mock for URL checks. */
function stubFetch(body: unknown) {
  const mock = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
  vi.stubGlobal('fetch', mock)
  return mock
}

describe('reliabilityTone', () => {
  it('matches the server bands and withholds a tone without data', () => {
    expect(reliabilityTone(null)).toBeNull()
    expect(reliabilityTone(90)).toBe('positive')
    expect(reliabilityTone(70)).toBe('positive')
    expect(reliabilityTone(69)).toBe('neutral')
    expect(reliabilityTone(45)).toBe('neutral')
    expect(reliabilityTone(44)).toBe('negative')
    expect(reliabilityTone(0)).toBe('negative')
  })
})

describe('barHeights', () => {
  it('scales to the peak and keeps small values visible', () => {
    expect(barHeights([10, 5, 0, 1])).toEqual([100, 50, 0, 10])
    expect(barHeights([100, 1])).toEqual([100, 6])
  })

  it('copes with empty and all-zero series', () => {
    expect(barHeights([])).toEqual([])
    expect(barHeights([0, 0])).toEqual([0, 0])
  })
})

describe('fillSeries', () => {
  // Half past the hour, so the newest hourly bucket is 10:00.
  const now = new Date('2026-11-14T10:30:00Z')

  it('gives a 24 hour window one bucket per hour, quiet hours included', () => {
    const out = fillSeries([{ at: '2026-11-14T09:00', added: 4 }], 24, now)
    expect(out).toHaveLength(24)
    expect(out[23]).toEqual({ at: '2026-11-14T10:00', added: 0 })
    expect(out[22]).toEqual({ at: '2026-11-14T09:00', added: 4 })
    expect(out[0].at).toBe('2026-11-13T11:00')
  })

  it('uses one bucket per day beyond two days, matching the server', () => {
    const out = fillSeries([{ at: '2026-11-13', added: 9 }], 168, now)
    expect(out).toHaveLength(7)
    expect(out.map((b) => b.at).slice(-2)).toEqual(['2026-11-13', '2026-11-14'])
    expect(out[5].added).toBe(9)
  })

  it('copes with an empty series', () => {
    expect(fillSeries([], 24, now).every((b) => b.added === 0)).toBe(true)
  })
})

describe('formatting', () => {
  it('shortens durations', () => {
    expect(formatDuration(850)).toBe('850 ms')
    expect(formatDuration(3200)).toBe('3.2 s')
    expect(formatDuration(65_000)).toBe('1m 05s')
  })

  it('formats percentages and ages, with a dash or "never" for no data', () => {
    expect(percent(0.756)).toBe('76%')
    expect(percent(null)).toBe('–')
    expect(minutesAgo(null)).toBe('never')
    expect(minutesAgo(0)).toBe('just now')
    expect(minutesAgo(12)).toBe('12 min ago')
    expect(minutesAgo(180)).toBe('3 h ago')
    expect(minutesAgo(60 * 24 * 5)).toBe('5 d ago')
  })

  it('labels dates in UTC so every reader sees the same day', () => {
    expect(dayLabel('2026-01-05')).toMatch(/5/)
  })

  it('treats a pipeline as stale only well past the 15-minute schedule', () => {
    expect(STALE_AFTER_MINUTES).toBeGreaterThanOrEqual(30)
  })
})

describe('the new endpoints', () => {
  it('request the timeline, sources and observability windows', async () => {
    const mock = stubFetch({})
    await api.timeline(7)
    await api.sources()
    await api.observability()
    await api.observability(168)
    const urls = mock.mock.calls.map((c) => (c as unknown as [string])[0])
    expect(urls).toEqual(['/api/stories/7/timeline', '/api/sources', '/api/observability?hours=24', '/api/observability?hours=168'])
  })
})
