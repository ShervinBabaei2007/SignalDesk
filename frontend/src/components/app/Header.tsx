// Top bar with branding, ingest button, feeds, watchlist and settings access.
import { useEffect, useState, type MouseEvent } from 'react'
import { Activity, Bell, CircleHelp, FileSpreadsheet, Loader2, Mail, Menu, RefreshCw, Rss, Settings as SettingsIcon, ShieldCheck, UserRoundX, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { AppLink as Link } from '@/components/app/AppLink'
import { FeedsDialog } from '@/components/app/FeedsDialog'
import { LockedDialog, LockMark } from '@/components/app/LockedDialog'
import { PipelineDialog } from '@/components/app/PipelineDialog'
import { SettingsSheet } from '@/components/app/SettingsSheet'
import { SourcesDialog } from '@/components/app/SourcesDialog'
import { WatchlistDialog } from '@/components/app/WatchlistDialog'
import { useDashboard } from '@/hooks/useDashboard'
import { useMode } from '@/hooks/useMode'
import { useSettings } from '@/hooks/useSettings'
import { api, ApiError, authMessage } from '@/lib/api'
import { copyBrief } from '@/lib/briefActions'
import type { Feature } from '@/lib/mode'
import { leaveDashboard, NAV_EVENTS, navigateTo, openWelcome, type Tool } from '@/lib/nav'

/** Sticky top bar with the logo, ingest button, tool dialogs and a mobile menu. */
export function Header() {
  const { health, ingesting, runIngest, clearFilters, digest } = useDashboard()
  const { token, saveToken } = useSettings()
  const { mode, locked, prefix } = useMode()
  const [lockedFeature, setLockedFeature] = useState<Feature | null>(null)
  // Everyone but the owner can leave: a workspace is kept for when they come back, the demo is simply ended.
  const canLeave = mode !== 'owner'
  const leaveLabel = mode === 'workspace' ? 'Leave workspace' : 'Exit demo'
  const [feedsOpen, setFeedsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [watchOpen, setWatchOpen] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [pipelineOpen, setPipelineOpen] = useState(false)

  /** Takes the visitor back to the dashboard with filters cleared and scrolled to the top. */
  const onLogo = (e: MouseEvent) => {
    e.preventDefault()
    clearFilters()
    navigateTo('/')
  }

  /** Returns to the landing page, keeping a workspace token so it can resume but dropping a demo token. */
  const leave = () => {
    if (mode === 'workspace') {
      toast.success('Your workspace is saved in this browser')
    } else {
      saveToken('')
      toast.success('Demo ended')
    }
    leaveDashboard()
  }

  /** Sends the daily brief from the mobile menu and reports the outcome in a toast. */
  const sendBrief = async () => {
    try {
      const r = await api.sendDigest()
      toast.success(`Daily brief sent via ${r.sent.join(' + ')}`)
    } catch (err) {
      const e = err as ApiError
      let message = e.message
      if (e.status === 400) message = 'No delivery channel configured — set Slack or SMTP settings'
      else if (e.status === 401) message = authMessage(token)
      toast.error(message)
    }
  }

  /** Close the mobile menu, then run the chosen action. */
  const fromMenu = (action: () => void) => () => {
    setMenuOpen(false)
    action()
  }

  /** Open Feeds, or explain the lock in the demo. */
  const openFeeds = () => (locked('feeds') ? setLockedFeature('feeds') : setFeedsOpen(true))
  /** Open the Watchlist, or explain the lock in the demo. */
  const openWatch = () => (locked('watchlist') ? setLockedFeature('watchlist') : setWatchOpen(true))
  /** Send the daily brief, or explain the lock in the demo. */
  const briefAction = () => {
    if (locked('brief')) setLockedFeature('brief')
    else if (mode === 'workspace') void copyBrief(digest) // a workspace has no delivery channel of its own
    else void sendBrief()
  }
  /** Explain the CSV export lock in the demo. */
  const explainExport = () => setLockedFeature('export')
  /** Props for a CSV button: a download link, or `onLocked` on click while export is locked. */
  const exportProps = (onLocked: () => void) =>
    locked('export') ? { onClick: onLocked } : { render: <a href="/api/articles/export.csv" download /> }

  // The checklist asks for tool dialogs by event, since the dialogs live here.
  useEffect(() => {
    /** Open the requested tool dialog (gated like the buttons). */
    const onTool = (e: Event) => {
      const tool = (e as CustomEvent<Tool>).detail
      if (tool === 'feeds') openFeeds()
      if (tool === 'watchlist') openWatch()
    }
    /** Show the locked prompt another component asked for. */
    const onLocked = (e: Event) => setLockedFeature((e as CustomEvent<Feature>).detail)
    window.addEventListener(NAV_EVENTS.openTool, onTool)
    window.addEventListener(NAV_EVENTS.locked, onLocked)
    return () => {
      window.removeEventListener(NAV_EVENTS.openTool, onTool)
      window.removeEventListener(NAV_EVENTS.locked, onLocked)
    }
  })

  const ingest = (
    <Button
      onClick={() => void runIngest()}
      disabled={ingesting}
      aria-label="Ingest feeds"
      className="h-9 bg-emerald-600 px-3 text-sm font-medium text-white hover:bg-emerald-700 focus-visible:ring-emerald-600/40 disabled:opacity-70 dark:bg-emerald-500 dark:text-emerald-950 dark:hover:bg-emerald-400"
    >
      {ingesting ? <Loader2 className="size-4 animate-spin sm:mr-1.5" /> : <RefreshCw className="size-4 sm:mr-1.5" />}
      <span className="hidden sm:inline">{ingesting ? 'Checking feeds…' : 'Ingest feeds'}</span>
    </Button>
  )

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[96rem] items-center justify-between gap-3 px-4 sm:px-6">
        <Link
          to="/"
          onClick={onLogo}
          aria-label="SignalDesk home"
          className="group flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground transition-transform group-hover:scale-105">
            <Zap className="size-4 fill-current" aria-hidden />
          </span>
          <span className="leading-tight">
            <span className="block text-[15px] font-bold tracking-tight">SignalDesk</span>
            <span className="hidden text-xs whitespace-nowrap text-muted-foreground 2xl:block">News intelligence, on autopilot</span>
          </span>
        </Link>

        <div className="flex items-center gap-1.5">
          {(mode === 'workspace' || mode === 'demo') && (
            <Badge variant="secondary" className="mr-1 hidden sm:inline-flex lg:hidden xl:inline-flex">
              {mode === 'workspace' ? 'Your workspace' : 'Demo tour'}
            </Badge>
          )}
          {health && (
            <Badge variant="outline" className="mr-1 hidden gap-1.5 text-positive xl:inline-flex">
              <span className="size-1.5 rounded-full bg-positive shadow-[0_0_6px_var(--positive)]" />
              API healthy · {health.articles} articles
            </Badge>
          )}
          <div className="hidden items-center gap-1 lg:flex">
            <Button variant="ghost" title={locked('export') ? 'Export CSV (workspace only)' : 'Export CSV'} aria-label="Export CSV" {...exportProps(explainExport)}>
              <FileSpreadsheet data-icon="inline-start" /> <span className="hidden xl:inline">CSV</span>
              <LockMark feature="export" />
            </Button>
            <Button variant="ghost" title="Feeds" aria-label="Feeds" onClick={openFeeds}>
              <Rss data-icon="inline-start" /> <span className="hidden xl:inline">Feeds</span>
              <LockMark feature="feeds" />
            </Button>
            <Button variant="ghost" title="Watchlist" aria-label="Watchlist" onClick={openWatch}>
              <Bell data-icon="inline-start" /> <span className="hidden xl:inline">Watchlist</span>
              <LockMark feature="watchlist" />
            </Button>
            <Button variant="ghost" title="Source profiles" aria-label="Source profiles" onClick={() => setSourcesOpen(true)}>
              <ShieldCheck data-icon="inline-start" /> <span className="hidden xl:inline">Sources</span>
            </Button>
            <Button variant="ghost" title="Pipeline health" aria-label="Pipeline health" onClick={() => setPipelineOpen(true)}>
              <Activity data-icon="inline-start" /> <span className="hidden xl:inline">Pipeline</span>
            </Button>
            {prefix && (
              <Button variant="ghost" title="Help" aria-label="Help" onClick={openWelcome}>
                <CircleHelp data-icon="inline-start" /> <span className="hidden xl:inline">Help</span>
              </Button>
            )}
            <Button variant="ghost" title="Settings" aria-label="Settings" onClick={() => setSettingsOpen(true)}>
              <SettingsIcon data-icon="inline-start" /> <span className="hidden xl:inline">Settings</span>
            </Button>
          </div>
          {canLeave && (
            <Button variant="outline" className="hidden sm:inline-flex" title={leaveLabel} aria-label={leaveLabel} onClick={leave}>
              <UserRoundX data-icon="inline-start" /> <span className="hidden xl:inline">{leaveLabel}</span>
            </Button>
          )}
          {ingest}
          <Button variant="outline" size="icon-lg" className="lg:hidden" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
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
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(openFeeds)}>
              <Rss data-icon="inline-start" /> Manage feeds <LockMark feature="feeds" />
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(openWatch)}>
              <Bell data-icon="inline-start" /> Watchlist <LockMark feature="watchlist" />
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(briefAction)}>
              <Mail data-icon="inline-start" /> {mode === 'workspace' || locked('brief') ? 'Copy daily brief' : 'Send daily brief'} <LockMark feature="brief" />
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" {...exportProps(fromMenu(explainExport))}>
              <FileSpreadsheet data-icon="inline-start" /> Export CSV <LockMark feature="export" />
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setSourcesOpen(true))}>
              <ShieldCheck data-icon="inline-start" /> Source profiles
            </Button>
            <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(() => setPipelineOpen(true))}>
              <Activity data-icon="inline-start" /> Pipeline health
            </Button>
            {prefix && (
              <Button variant="outline" size="lg" className="h-11 justify-start" onClick={fromMenu(openWelcome)}>
                <CircleHelp data-icon="inline-start" /> Help and tour
              </Button>
            )}
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
      <LockedDialog feature={lockedFeature} onClose={() => setLockedFeature(null)} />
    </header>
  )
}
