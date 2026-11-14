// Root layout and dashboard view; `router.tsx` decides which page renders inside the layout.
import type { ReactNode } from 'react'
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { Link, Outlet, ScrollRestoration, useLocation } from 'react-router'
import { ArticleFeed } from '@/components/app/ArticleFeed'
import { DailyBrief } from '@/components/app/DailyBrief'
import { Filters } from '@/components/app/Filters'
import { GetStartedCard } from '@/components/app/GetStartedCard'
import { Header } from '@/components/app/Header'
import { Onboarding } from '@/components/app/Onboarding'
import { Sidebar } from '@/components/app/Sidebar'
import { StatsRow } from '@/components/app/StatsRow'
import { Button } from '@/components/ui/button'
import { useMode } from '@/hooks/useMode'
import { navigateAbsolute } from '@/lib/nav'

/** The home view: stats, filters, trend, daily brief and the article feed. */
export function Dashboard() {
  return (
    <div className="space-y-4">
      <GetStartedCard />
      <StatsRow />
      <Filters />
      <div className="grid items-start gap-5 lg:grid-cols-[17rem_minmax(0,1fr)]">
        {/* Categories only: short enough to stay on screen, so no inner scrollbar */}
        <div className="compact-hide sidebar-sticky hidden lg:block">
          <Sidebar />
        </div>
        <div className="min-w-0 lg:[html[data-compact=on]_&]:col-span-2">
          <DailyBrief />
          <ArticleFeed />
        </div>
      </div>
    </div>
  )
}

/** Slim bar under the header in the demo: says what is limited and offers the workspace. */
function DemoBanner() {
  const { prefix } = useMode()
  if (prefix !== 'demo') return null
  return (
    <div className="border-b bg-muted/50">
      <div className="mx-auto flex max-w-[96rem] flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-1.5 text-[13px] sm:px-6">
        <p className="text-muted-foreground">
          You’re on the demo tour. Feeds, watchlist, copying the brief and CSV export unlock in your own workspace.
        </p>
        <Button size="sm" variant="link" className="h-auto p-0" onClick={() => navigateAbsolute('/workspace')}>
          Open a workspace
        </Button>
      </div>
    </div>
  )
}

/** App shell with header, motion settings and the active route (or `children`, used by the error page). */
export function RootLayout({ children }: { children?: ReactNode }) {
  const { pathname } = useLocation()
  return (
    // Respect the OS "reduce motion" setting for every animation below.
    <MotionConfig reducedMotion="user">
      <ScrollRestoration />
      <div className="min-h-dvh">
        <Header />
        <DemoBanner />
        <Onboarding />
        <main className="mx-auto max-w-[96rem] px-4 py-5 sm:px-6">
          <AnimatePresence mode="wait" initial={false}>
            {/* A key per page (and per article or story id) makes every navigation animate */}
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {children ?? <Outlet />}
            </motion.div>
          </AnimatePresence>
        </main>
        <footer className="border-t py-5 text-center text-xs text-muted-foreground">
          <strong className="text-foreground">SignalDesk</strong> · FastAPI + React · sentiment, topics &amp; summaries
          computed on ingest · <Link to="/welcome" className="underline-offset-2 hover:underline">About</Link>
        </footer>
      </div>
    </MotionConfig>
  )
}
