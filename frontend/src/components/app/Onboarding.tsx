// First-visit welcome dialog for the demo and for a workspace, plus the step tracking that feeds the checklist.
import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { useLocation } from 'react-router'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useDashboard } from '@/hooks/useDashboard'
import { useMode } from '@/hooks/useMode'
import { getAuthStatus } from '@/lib/api'
import { FEATURES, type PrefixMode } from '@/lib/mode'
import { NAV_EVENTS, navigateAbsolute } from '@/lib/nav'
import { markStep, setDismissed, setWelcomed, useOnboarding } from '@/lib/onboarding'

/** One page of the welcome dialog. */
interface Slide {
  title: string
  body: string
  points?: string[]
}

/** The welcome pages for a mode; the workspace's first page needs to know how long data is kept. */
function slidesFor(mode: PrefixMode, ttlDays: number): Slide[] {
  if (mode === 'demo') {
    return [
      {
        title: 'Welcome to the SignalDesk demo',
        body: 'A guided look at how SignalDesk turns a flood of news reports into stories you can compare. Everything here runs on a shared set of sample feeds.',
      },
      {
        title: 'What you can do here',
        body: 'The demo includes the core of the app:',
        points: [
          'Browse stories that group reports from different outlets',
          'Read articles with a summary, sentiment and information score',
          'Filter by topic, sentiment, outlet or date',
          'Run a live ingest to fetch fresh articles for a couple of hours',
        ],
      },
      {
        title: 'What a workspace adds',
        body: 'These are visible in the demo but locked. They unlock in your own workspace, which is free and needs no sign-up:',
        points: Object.values(FEATURES).map((f) => f.title),
      },
    ]
  }
  return [
    {
      title: 'Your private workspace',
      body: `This workspace is yours alone: your own feeds, watch terms and articles, kept apart from everyone else. It is deleted automatically after ${ttlDays} days.`,
    },
    {
      title: 'Set it up in three steps',
      body: 'The Get started card on your dashboard walks you through it:',
      points: ['Add a feed: paste the RSS link of a site you follow', 'Run an ingest to pull in its articles', 'Watch a term to get alerts when several outlets cover it'],
    },
    {
      title: 'Good to know',
      body: 'Your workspace is saved in this browser. Leaving keeps it for next time; clearing the browser’s site data loses it.',
      points: ['Copy or download the daily brief', 'Export your articles as CSV', 'Save articles to read later'],
    },
  ]
}

/** The welcome dialog itself: a few pages with Back, Next and a final "Get started". */
function WelcomeDialog({ mode, open, onClose }: { mode: PrefixMode; open: boolean; onClose: () => void }) {
  const [page, setPage] = useState(0)
  const [ttlDays, setTtlDays] = useState(7)

  // The retention period comes from the server's settings.
  useEffect(() => {
    if (open) void getAuthStatus().then((s) => setTtlDays(s.workspace_ttl_days ?? 7))
  }, [open])

  const slides = slidesFor(mode, ttlDays)
  const slide = slides[Math.min(page, slides.length - 1)]
  const last = page >= slides.length - 1

  /** Close the dialog and rewind it for the next time it is opened. */
  const close = () => {
    onClose()
    setPage(0)
  }

  /** Close the dialog with the checklist card showing. */
  const finish = () => {
    setDismissed(mode, false)
    close()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <p className="text-xs font-semibold tracking-wide text-ai uppercase">
            {mode === 'demo' ? 'Demo tour' : 'Your workspace'} · {page + 1} of {slides.length}
          </p>
          <DialogTitle className="text-xl">{slide.title}</DialogTitle>
          <DialogDescription>{slide.body}</DialogDescription>
        </DialogHeader>
        {slide.points && (
          <ul className="grid gap-2 text-sm">
            {slide.points.map((p) => (
              <li key={p} className="flex items-start gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-positive" aria-hidden />
                {p}
              </li>
            ))}
          </ul>
        )}
        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" onClick={page === 0 ? close : () => setPage(page - 1)}>
            {page === 0 ? 'Skip' : 'Back'}
          </Button>
          {last && mode === 'demo' ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button variant="outline" onClick={() => { close(); navigateAbsolute('/workspace') }}>Open a workspace</Button>
              <Button onClick={finish}>Start exploring</Button>
            </div>
          ) : (
            <Button onClick={last ? finish : () => setPage(page + 1)}>
              {last ? 'Get started' : 'Next'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Lives in the layout: shows the welcome dialog on a mode's first visit and ticks steps as the visitor goes. */
export function Onboarding() {
  const { prefix } = useMode()
  const { pathname } = useLocation()
  const { hasActiveFilters } = useDashboard()
  const state = useOnboarding(prefix ?? 'demo')
  const [open, setOpen] = useState(false)

  // Open on the first visit to this mode, and whenever the Help button asks.
  useEffect(() => {
    if (prefix && !state.welcomed) setOpen(true)
  }, [prefix, state.welcomed])
  useEffect(() => {
    /** Reopen the dialog from the Help button. */
    const on = () => setOpen(true)
    window.addEventListener(NAV_EVENTS.openWelcome, on)
    return () => window.removeEventListener(NAV_EVENTS.openWelcome, on)
  }, [])

  // Visiting a story or article page completes that step.
  useEffect(() => {
    if (!prefix) return
    if (/\/story\/\d+$/.test(pathname)) markStep(prefix, 'story')
    if (/\/article\/\d+$/.test(pathname)) markStep(prefix, 'article')
  }, [prefix, pathname])

  // Using any filter completes the filter step.
  useEffect(() => {
    if (prefix && hasActiveFilters) markStep(prefix, 'filter')
  }, [prefix, hasActiveFilters])

  if (!prefix) return null
  return (
    <WelcomeDialog
      mode={prefix}
      open={open}
      onClose={() => {
        setOpen(false)
        setWelcomed(prefix)
      }}
    />
  )
}
