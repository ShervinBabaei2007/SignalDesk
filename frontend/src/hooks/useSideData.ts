import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type Digest, type Feed, type Health, type Stats, type TrendingStory } from '@/lib/api'

/** The numbers around the feed: stats, daily brief, hot stories, server health and the feed list. */
export function useSideData() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [digest, setDigest] = useState<Digest | null>(null)
  const [trending, setTrending] = useState<TrendingStory[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [feeds, setFeeds] = useState<Feed[]>([])

  // Each part loads on its own: one failing endpoint must not blank the others.
  const reloadSide = useCallback(async () => {
    const [s, d, t, h, fs] = await Promise.allSettled([
      api.stats(), api.digest(), api.trending(), api.health(), api.feeds(),
    ])
    if (s.status === 'fulfilled') setStats(s.value)
    if (d.status === 'fulfilled') setDigest(d.value)
    if (t.status === 'fulfilled') setTrending(t.value)
    if (h.status === 'fulfilled') setHealth(h.value)
    if (fs.status === 'fulfilled') setFeeds(fs.value)
  }, [])

  useEffect(() => {
    void reloadSide()
  }, [reloadSide])

  const refreshFeeds = useCallback(async () => {
    setFeeds(await api.feeds())
  }, [])

  const sources = useMemo(() => feeds.map((f) => f.name).sort(), [feeds])
  /** Articles that belong to the hot stories (matches the `hot` feed filter). */
  const hotCount = useMemo(() => trending.reduce((n, t) => n + t.reports, 0), [trending])

  return { stats, digest, trending, health, feeds, sources, hotCount, reloadSide, refreshFeeds }
}
