import { useState } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { useSettings } from '@/hooks/useSettings'
import { cn } from '@/lib/utils'

const THEMES = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
] as const

export function SettingsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { theme, setTheme } = useTheme()
  const { compact, setCompact, token, saveToken } = useSettings()
  const [draft, setDraft] = useState(token)

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

          <section className="space-y-2.5">
            <Label htmlFor="token">API token</Label>
            <p className="text-[13px] leading-snug text-muted-foreground">
              Only needed if the server sets <code className="rounded bg-muted px-1">API_TOKEN</code>. It is required for ingest, feed changes and sending the brief.
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
