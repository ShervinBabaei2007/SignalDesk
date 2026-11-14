// Dialog to create, pause and delete watchlist terms.
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Bell, BellRing, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { useDashboard } from '@/hooks/useDashboard'
import { useSettings } from '@/hooks/useSettings'
import { api, ApiError, authMessage, type Watch } from '@/lib/api'
import { TOPIC_EMOJI } from '@/lib/format'
import { completeStep } from '@/lib/nav'
import { cn } from '@/lib/utils'

/** Select value meaning any topic. */
const ANY = 'any'
/** Minimum-outlet choices for a watch. */
const OUTLET_OPTIONS = [
  { value: '1', label: 'Any single outlet' },
  { value: '2', label: '2+ outlets (recommended)' },
  { value: '3', label: '3+ outlets' },
  { value: '4', label: '4+ outlets' },
]

/** One watch with a pause switch and delete button. */
function WatchRow({ watch, onToggle, onDelete }: { watch: Watch; onToggle: (on: boolean) => void; onDelete: () => void }) {
  return (
    <li className={cn('flex items-center gap-3 rounded-lg border bg-background/50 px-3 py-2.5', !watch.is_active && 'opacity-60')}>
      <Switch checked={watch.is_active} onCheckedChange={onToggle} aria-label={`${watch.is_active ? 'Pause' : 'Resume'} watching ${watch.term}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-semibold">{watch.term}</span>
          {watch.topic && (
            <Badge variant="secondary" className="font-normal">
              {TOPIC_EMOJI[watch.topic] ?? '📰'} {watch.topic}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {watch.min_outlets === 1 ? 'Any single outlet' : `When ${watch.min_outlets}+ outlets cover it`} ·{' '}
          {watch.matches} {watch.matches === 1 ? 'story' : 'stories'} right now
        </p>
      </div>
      <Button variant="ghost" size="icon" aria-label={`Stop watching ${watch.term}`} className="text-negative hover:text-negative" onClick={onDelete}>
        <Trash2 />
      </Button>
    </li>
  )
}

/** Follow a word or phrase: it flags matching stories in the feed and alerts you when a new one breaks. */
export function WatchlistDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { stats, health, refreshAll } = useDashboard()
  const { token } = useSettings()
  const [watches, setWatches] = useState<Watch[]>([])
  const [term, setTerm] = useState('')
  const [topic, setTopic] = useState(ANY)
  const [minOutlets, setMinOutlets] = useState('2')
  const [busy, setBusy] = useState(false)
  const topicOptions = [
    { value: ANY, label: 'Any topic' },
    ...Object.keys(stats?.topic_breakdown ?? {})
      .sort()
      .map((t) => ({ value: t, label: `${TOPIC_EMOJI[t] ?? '📰'} ${t}` })),
  ]
  const channels = health?.features?.digest_delivery ?? []

  /** Fetches the current watches from the API. */
  const load = useCallback(async () => {
    try {
      setWatches(await api.watches())
    } catch (err) {
      toast.error(`Could not load the watchlist: ${(err as Error).message}`)
    }
  }, [])

  // Reload the watchlist every time the dialog opens so match counts are fresh.
  useEffect(() => {
    if (open) void load()
  }, [open, load])

  /** Runs a watchlist change with a busy flag, then reloads it or toasts the error. */
  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
      await load()
      void refreshAll() // the feed badges depend on the watchlist
    } catch (err) {
      const e = err as ApiError
      toast.error(e.status === 401 ? authMessage(token) : e.message)
    } finally {
      setBusy(false)
    }
  }

  /** Submits the add-watch form and clears the term on success. */
  const add = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      await api.addWatch(term, topic === ANY ? null : topic, Number(minOutlets))
      completeStep('watch')
      setTerm('')
      toast.success(`Watching “${term.trim()}”`)
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <BellRing className="size-4 text-link" aria-hidden /> Watchlist
          </DialogTitle>
          <DialogDescription>
            Follow a word or phrase. Matching stories get a 🔔 badge in the feed, and you are told when a new one breaks.{' '}
            {channels.length
              ? `Alerts are also sent to ${channels.join(' and ')}.`
              : 'To also get alerts by Slack or email, add them to your .env (see the README).'}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-64 pr-3">
          {watches.length === 0 ? (
            <div className="grid place-items-center gap-1 py-8 text-center">
              <Bell className="size-7 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">Nothing watched yet</p>
              <p className="max-w-xs text-xs text-muted-foreground">Try a company, a place or a phrase like “ground stop”.</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {watches.map((w) => (
                <WatchRow
                  key={w.id}
                  watch={w}
                  onToggle={(on) => void run(async () => { await api.setWatchActive(w.id, on) })}
                  onDelete={() => void run(async () => { await api.deleteWatch(w.id) })}
                />
              ))}
            </ul>
          )}
        </ScrollArea>

        <Separator />

        <form onSubmit={add} className="grid gap-2">
          <Input
            placeholder="Word or phrase to watch, e.g. “OpenAI” or “ground stop”"
            aria-label="Word or phrase to watch"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            maxLength={100}
            required
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <Select items={topicOptions} value={topic} onValueChange={(v) => setTopic(String(v ?? ANY))}>
              <SelectTrigger aria-label="Topic" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {topicOptions.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select items={OUTLET_OPTIONS} value={minOutlets} onValueChange={(v) => setMinOutlets(String(v ?? '2'))}>
              <SelectTrigger aria-label="Minimum outlets" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {OUTLET_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={busy || !term.trim()}>
            <Plus data-icon="inline-start" /> Add to watchlist
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
