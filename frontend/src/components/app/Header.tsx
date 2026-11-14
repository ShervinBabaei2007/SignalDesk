// Top bar with branding, ingest button, feeds, watchlist and settings access.
import { useState, type MouseEvent } from 'react'
import { Activity, Bell, FileSpreadsheet, Loader2, Mail, Menu, RefreshCw, Rss, Settings as SettingsIcon, ShieldCheck, UserRoundX, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/ui/shimmer-button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { FeedsDialog } from '@/components/app/FeedsDialog'
import { PipelineDialog } from '@/components/app/PipelineDialog'
import { SettingsSheet } from '@/components/app/SettingsSheet'
import { SourcesDialog } from '@/components/app/SourcesDialog'
import { WatchlistDialog } from '@/components/app/WatchlistDialog'
import { useDashboard } from '@/hooks/useDashboard'
import { goHome, leaveDashboard } from '@/hooks/useRoute'
import { useSettings } from '@/hooks/useSettings'
import { api, ApiError, authMessage, sessionMode } from '@/lib/api'

/** The app header. */
export function Header() {
  const { health, ingesting, runIngest, clearFilters } = useDashboard()
  const { token, saveToken } = useSettings()
  const mode = sessionMode(token)
  // Everyone but the owner can leave: a workspace is kept for when they come back, the demo is simply ended.
  const canLeave = mode !== 'owner'
  const leaveLabel = mode === 'workspace' ? 'Leave workspace' : 'Exit demo'
  const [feedsOpen, setFeedsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [watchOpen, setWatchOpen] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [pipelineOpen, setPipelineOpen] = useState(false)

  // The logo always means "take me home": back to the dashboard, filters cleared, scrolled to top.
  const onLogo = (e: MouseEvent) => {
    e.preventDefault()
    clearFilters()
    goHome()
  }

  /** Go back to the landing page. A workspace token stays, so "Open my workspace" resumes it; a demo token is dropped. */
  const leave = () => {
    if (mode === 'workspace') {
      toast.success('Your workspace is saved in this browser')
    } else {
      saveToken('')
      toast.success('Demo ended')
    }
    leaveDashboard()
  }

  const sendBrief = async () => {
    try {
      const r = await api.sendDigest()
      toast.success(`Daily brief sent via ${r.sent.join(' + ')}`)
    } catch (err) {
      const e = err as ApiError
      toast.error(e.status === 400 ? 'No delivery channel configured — set Slack or SMTP settings' : e.status === 401 ? authMessage(token) : e.message)
    }
  }

  /** Close the mobile menu, then run the chosen action. */
  const fromMenu = (action: () => void) => () => {
    setMenuOpen(false)
    action()
  }

  const ingest = (
    <ShimmerButton
      onClick={() => void runIngest()}
      disabled={ingesting}
      aria-label="Ingest feeds"
      background="var(--primary)"
      shimmerColor="#ffffff"
      borderRadius="0.625rem"
      className="h-9 px-3 text-sm font-medium disabled:opacity-70"
    >
      {ingesting ? <Loader2 className="size-4 animate-spin sm:mr-1.5" /> : <RefreshCw className="size-4 sm:mr-1.5" />}
      <span className="hidden sm:inline">{ingesting ? 'Checking feeds…' : 'Ingest feeds'}</span>
    </ShimmerButton>
  )

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4">
        <a
          href="#/"
          onClick={onLogo}
          aria-label="SignalDesk home"
          className="group flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground transition-transform group-hover:scale-105">
            <Zap className="size-4 fill-current" aria-hidden />
          </span>
          <span className="leading-tight">
            <span className="block text-[15px] font-bold tracking-tight">SignalDesk</span>
            <span className="hidden text-xs text-muted-foreground sm:block">News intelligence, on autopilot</span>
          </span>
        </a>

        <div className="flex items-center gap-1.5">
          {(mode === 'workspace' || mode === 'demo') && (
            <Badge variant="secondary" className="mr-1 hidden sm:inline-flex">
              {mode === 'workspace' ? 'Your workspace' : 'Demo tour'}
            </Badge>
          )}
          {health && (
            <Badge variant="outline" className="mr-1 hidden gap-1.5 text-positive lg:inline-flex">
              <span className="size-1.5 rounded-full bg-positive shadow-[0_0_6px_var(--positive)]" />
              API healthy · {health.articles} articles
            </Badge>
          )}
          <div className="hidden items-center gap-1 md:flex">
            <Button variant="ghost" render={<a href="/api/articles/export.csv" download />}>
              <FileSpreadsheet data-icon="inline-start" /> CSV
            </Button>
            <Button variant="ghost" onClick={() => setFeedsOpen(true)}>
              <Rss data-icon="inline-start" /> Feeds
            </Button>
            <Button variant="ghost" onClick={() => setWatchOpen(true)}>
              <Bell data-icon="inline-start" /> Watchlist
            </Button>
            <Button variant="ghost" onClick={() => setSourcesOpen(true)}>
              <ShieldCheck data-icon="inline-start" /> Sources
            </Button>
            <Button variant="ghost" onClick={() => setPipelineOpen(true)}>
              <Activity data-icon="inline-start" /> Pipeline
            </Button>
            <Button variant="ghost" onClick={() => setSettingsOpen(true)}>
              <SettingsIcon data-icon="inline-start" /> Settings
            </Button>
          </div>
          {canLeave && (
            <Button variant="outline" className="hidden sm:inline-flex" onClick={leave}>
              <UserRoundX data-icon="inline-start" /> {leaveLabel}
            </Button>
          )}
          {ingest}
          <Button variant="outline" size="icon-lg" className="md:hidden" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
            <Menu />
          </Button>
        </div>
      </div>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="bottom" className="gap-2 rounded-t-2xl pb-6">
          <SheetHeader>
            <SheetTitle>Menu</SheetTitle>
            <SheetDescription>{health ? `API healthy · ${health.articles} articles · ${health.feeds} feeds` : 'SignalDesk'}</SheetDescription>
          </SheetHeader>
          <div className="grid gap-2 px-4">
            <Button size="lg" className="h-11 justify-start" onClick={fromMenu(() => void runIngest())}>
              <RefreshCw data-icon="inline-start" /> Ingest feeds
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setFeedsOpen(true))}>
              <Rss data-icon="inline-start" /> Manage feeds
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setWatchOpen(true))}>
              <Bell data-icon="inline-start" /> Watchlist
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => void sendBrief())}>
              <Mail data-icon="inline-start" /> Send daily brief
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" render={<a href="/api/articles/export.csv" download />}>
              <FileSpreadsheet data-icon="inline-start" /> Export CSV
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setSourcesOpen(true))}>
              <ShieldCheck data-icon="inline-start" /> Source profiles
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setPipelineOpen(true))}>
              <Activity data-icon="inline-start" /> Pipeline health
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setSettingsOpen(true))}>
              <SettingsIcon data-icon="inline-start" /> Settings
            </Button>
            {canLeave && (
              <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(leave)}>
                <UserRoundX data-icon="inline-start" /> {leaveLabel}
              </Button>
            )}
          </div>
        </SheetContent>
      </Sheet>

      <FeedsDialog open={feedsOpen} onOpenChange={setFeedsOpen} />
      <WatchlistDialog open={watchOpen} onOpenChange={setWatchOpen} />
      <SettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
      <SourcesDialog open={sourcesOpen} onOpenChange={setSourcesOpen} />
      <PipelineDialog open={pipelineOpen} onOpenChange={setPipelineOpen} />
    </header>
  )
}
