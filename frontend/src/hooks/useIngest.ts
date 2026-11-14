import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { api, type ApiError } from '@/lib/api'

/** The "Ingest feeds" action: progress text, toasts (including watchlist alerts), then a refresh. */
export function useIngest(refreshAll: () => Promise<void>) {
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState('')

  const runIngest = useCallback(async () => {
    setIngesting(true)
    setIngestResult('Fetching feeds, removing duplicates and analyzing…')
    try {
      const r = await api.ingest()
      setIngestResult(`${r.added} new · ${r.fetched} fetched · ${r.skipped} duplicates skipped · ${r.duration_seconds}s`)
      toast.success(
        r.added ? `${r.added} new article${r.added === 1 ? '' : 's'} added` : 'All caught up — no new articles right now',
      )
      if (r.alerts?.length) {
        const first = r.alerts[0]
        toast(`🔔 ${r.alerts.length} watched ${r.alerts.length === 1 ? 'story' : 'stories'} matched`, {
          description: r.alerts.slice(0, 3).map((a) => `“${a.term}”: ${a.title}`).join('\n'),
          duration: 10000,
          action: {
            label: 'Open',
            onClick: () => {
              location.hash = first.cluster_id ? `#/story/${first.cluster_id}` : `#/article/${first.article_id}`
            },
          },
        })
      }
      await refreshAll()
    } catch (err) {
      const e = err as ApiError
      setIngestResult(e.message)
      toast.error(e.status === 429 ? 'Just checked — give the feeds a moment' : `Ingestion failed: ${e.message}`)
    } finally {
      setIngesting(false)
    }
  }, [refreshAll])

  return { ingesting, ingestResult, runIngest }
}
