// Dialog to view, add and remove RSS feeds.
import { useState, type FormEvent } from 'react'
import { Loader2, Plus, Sparkles, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { useDashboard } from '@/hooks/useDashboard'
import { useSettings } from '@/hooks/useSettings'
import { api, ApiError, authMessage, sessionMode, type Feed } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Short health text for a feed. */
function feedStatus(feed: Feed): string {
  if (!feed.last_status) return 'Not fetched yet'
  return feed.last_fetched_at ? `${feed.last_status} · ${timeAgo(feed.last_fetched_at)}` : feed.last_status
}

/** One feed row with its status and, when the visitor may remove it, a delete button. */
function FeedRow({ feed, onDelete, canRemove }: { feed: Feed; onDelete: () => void; canRemove: boolean }) {
  const failed = !!feed.last_status?.startsWith('error')
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border bg-background/50 px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-sm font-medium">{feed.name}</div>
        <div className="truncate font-mono text-[11px] text-muted-foreground">{feed.url}</div>
        <div className={cn('mt-0.5 text-[11px]', failed ? 'text-negative' : 'text-positive')}>
          {feedStatus(feed)}
        </div>
      </div>
      {canRemove ? (
        <Button variant="ghost" size="icon" aria-label={`Remove ${feed.name}`} className="text-negative hover:text-negative" onClick={onDelete}>
          <Trash2 />
        </Button>
      ) : (
        <span className="shrink-0 text-[11px] text-muted-foreground">Shared</span>
      )}
    </li>
  )
}

/** Dialog for listing the RSS feeds and, when allowed, adding or removing them. */
export function FeedsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { feeds, refreshFeeds } = useDashboard()
  const { token } = useSettings()
  const mode = sessionMode(token)
  const owner = mode === 'owner'
  const canEdit = owner || mode === 'workspace'
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)

  /** Runs a feed change with a busy flag, then reloads the list or toasts the error. */
  const guard = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
      await refreshFeeds()
    } catch (err) {
      const e = err as ApiError
      toast.error(e.status === 401 ? authMessage(token) : e.message)
    } finally {
      setBusy(false)
    }
  }

  /** Submits the add-feed form and clears it on success. */
  const add = (e: FormEvent) => {
    e.preventDefault()
    void guard(async () => {
      await api.addFeed(name.trim(), url.trim())
      setName('')
      setUrl('')
      toast.success('Feed added')
    })
  }

  /** Adds the built-in recommended feeds that are not configured yet. */
  const addRecommended = () =>
    void guard(async () => {
      const added = await api.addDefaultFeeds()
      toast.success(added.length ? `Added ${added.length} recommended feed${added.length === 1 ? '' : 's'}` : 'You already have all recommended feeds')
    })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-base">RSS feeds</DialogTitle>
          <DialogDescription>
            {mode === 'workspace'
              ? 'Shared feeds keep themselves up to date. Add your own and run Ingest feeds to pull them into your private workspace.'
              : 'Every active feed is fetched when you run an ingest, and automatically every 15 minutes.'}{' '}
            {feeds.length} feeds configured.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-72 pr-3">
          <ul className="space-y-2">
            {/* Workspace visitors can remove only their own feeds; the owner can remove any */}
            {feeds.map((f) => (
              <FeedRow key={f.id} feed={f} canRemove={owner || !f.shared} onDelete={() => void guard(async () => { await api.deleteFeed(f.id) })} />
            ))}
          </ul>
        </ScrollArea>

        {owner && (
          <Button variant="secondary" onClick={addRecommended} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Sparkles data-icon="inline-start" />}
            Add recommended feeds
          </Button>
        )}

        <Separator />

        {canEdit ? (
          <form onSubmit={add} className="grid gap-2">
            <Input placeholder="Feed name" aria-label="Feed name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
            <Input type="url" placeholder="https://example.com/rss.xml" aria-label="Feed URL" value={url} onChange={(e) => setUrl(e.target.value)} required />
            <Button type="submit" disabled={busy}>
              <Plus data-icon="inline-start" /> Add feed
            </Button>
          </form>
        ) : (
          <p className="text-sm text-muted-foreground">
            You are on the demo tour, which uses the shared feeds. Leave and choose <strong className="text-foreground">Open my workspace</strong> to
            add your own feeds.
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
