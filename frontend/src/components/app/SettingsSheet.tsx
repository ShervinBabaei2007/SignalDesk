// Side sheet for theme, layout, grouping and API token settings.
import { useState } from 'react'
import { Monitor, Moon, Sun, Trash2 } from 'lucide-react'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { useDashboard } from '@/hooks/useDashboard'
import { useSettings } from '@/hooks/useSettings'
import { api, sessionMode, type ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

/** Theme choices offered in settings. */
const THEMES = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
] as const

/** Side sheet for theme, calm mode, workspace reset and the API token. */
export function SettingsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { theme, setTheme } = useTheme()
  const { compact, setCompact, token, saveToken } = useSettings()
  const { refreshAll } = useDashboard()
  const [draft, setDraft] = useState(token)
  const [confirmReset, setConfirmReset] = useState(false)
  const inWorkspace = sessionMode(token) === 'workspace'

  /** Deletes this workspace's feeds, watchlist and articles, needing a second click to confirm. */
  const resetWorkspace = async () => {
    if (!confirmReset) {
      setConfirmReset(true)
      return
    }
    setConfirmReset(false)
    try {
      await api.resetWorkspace()
      toast.success('Workspace reset')
      await refreshAll()
    } catch (err) {
      toast.error(`Could not reset: ${(err as ApiError).message}`)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Settings</SheetTitle>
          <SheetDescription>Appearance and access. Saved in this browser only.</SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-4 pb-6">
          <section className="space-y-2.5">
            <Label>Theme</Label>
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1">
              {THEMES.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={theme === value}
                  onClick={() => setTheme(value)}
                  className={cn(
                    'flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-muted-foreground transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
                    theme === value && 'bg-background text-foreground shadow-sm',
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                </button>
              ))}
            </div>
          </section>

          <section className="flex items-start justify-between gap-4 rounded-lg border p-3.5">
            <div className="space-y-1">
              <Label htmlFor="compact">Calm mode</Label>
              <p className="text-[13px] leading-snug text-muted-foreground">
                Hides the side panels, charts and keyword chips so the feed feels lighter.
              </p>
            </div>
            <Switch id="compact" checked={compact} onCheckedChange={setCompact} />
          </section>

          {inWorkspace && (
            <section className="space-y-2.5 rounded-lg border p-3.5">
              <Label>Your workspace</Label>
              <p className="text-[13px] leading-snug text-muted-foreground">
                Your feeds, watchlist and articles are private to this browser. Reset wipes them; the shared news is not affected.
              </p>
              <Button variant={confirmReset ? 'destructive' : 'outline'} onClick={() => void resetWorkspace()} onBlur={() => setConfirmReset(false)}>
                <Trash2 data-icon="inline-start" /> {confirmReset ? 'Click again to confirm' : 'Reset workspace'}
              </Button>
            </section>
          )}

          <section className="space-y-2.5">
            <Label htmlFor="token">{inWorkspace ? 'Owner API token' : 'API token'}</Label>
            <p className="text-[13px] leading-snug text-muted-foreground">
              {inWorkspace
                ? 'For the site owner only: visitors never need this. Saving a token replaces your workspace in this browser.'
                : <>Only needed if the server sets <code className="rounded bg-muted px-1">API_TOKEN</code>. It is required for ingest, feed changes and sending the brief.</>}
            </p>
            <div className="flex gap-2">
              <Input id="token" type="password" autoComplete="off" placeholder="X-API-Key" value={draft} onChange={(e) => setDraft(e.target.value)} />
              <Button
                onClick={() => {
                  saveToken(draft)
                  toast.success(draft.trim() ? 'API token saved' : 'API token cleared')
                }}
              >
                Save
              </Button>
            </div>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  )
}
