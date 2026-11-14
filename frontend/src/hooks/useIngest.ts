// Hook that runs a feed ingest and reports the result.
import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { useSettings } from '@/hooks/useSettings'
import { api, sessionMode, type ApiError } from '@/lib/api'
import { completeStep, navigateTo } from '@/lib/nav'

/** The "Ingest feeds" action: progress text, toasts (including watchlist alerts), then a refresh. */
export function useIngest(refreshAll: () => Promise<void>) {
  const { token } = useSettings()
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState('')

  /** Run one ingest, report its outcome and any watchlist matches, then reload the dashboard. */
  const runIngest = useCallback(async () => {
    setIngesting(true)
    setIngestResult('Fetching feeds, removing duplicates and analyzing…')
    try {
      const r = await api.ingest()
      completeStep('ingest')
      setIngestResult(`${r.added} new · ${r.fetched} fetched · ${r.skipped} duplicates skipped · ${r.duration_seconds}s`)
      // A workspace ingests only its own feeds, so nothing fetched at all means it has none yet.
      if (sessionMode(token) === 'workspace' && r.fetched === 0 && r.skipped === 0) {
        toast('Add a feed first', { description: 'Open Feeds to add your own. The shared feeds refresh automatically.' })
      } else {
        toast.success(
          r.added ? `${r.added} new article${r.added === 1 ? '' : 's'} added` : 'All caught up — no new articles right now',
        )
      }
      if (r.alerts?.length) {
        const first = r.alerts[0]
        toast(`🔔 ${r.alerts.length} watched ${r.alerts.length === 1 ? 'story' : 'stories'} matched`, {
          // List at most three matches so the toast stays short.
          description: r.alerts.slice(0, 3).map((a) => `“${a.term}”: ${a.title}`).join('\n'),
          duration: 10000, // 10 s, longer than usual so there is time to click Open
          action: {
            label: 'Open',
            // Open the first match as a story when it is grouped, otherwise as a single article.
            onClick: () => {
              navigateTo(first.cluster_id ? `/story/${first.cluster_id}` : `/article/${first.article_id}`)
            },
          },
        })
      }
      await refreshAll()
    } catch (err) {
      const e = err as ApiError
      setIngestResult(e.message)
      // 429 means another ingest ran moments ago and the server is rate-limiting.
      toast.error(e.status === 429 ? 'Just checked — give the feeds a moment' : `Ingestion failed: ${e.message}`)
    } finally {
      setIngesting(false)
    }
  }, [refreshAll, token])

  return { ingesting, ingestResult, runIngest }
}
