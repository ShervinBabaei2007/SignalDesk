// Root layout: picks the dashboard, a story page or the reader from the URL hash.
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { ArticleFeed } from '@/components/app/ArticleFeed'
import { DailyBrief } from '@/components/app/DailyBrief'
import { Filters } from '@/components/app/Filters'
import { Header } from '@/components/app/Header'
import { Landing } from '@/components/app/Landing'
import { Reader } from '@/components/app/Reader'
import { StoryPage } from '@/components/app/StoryPage'
import { Sidebar } from '@/components/app/Sidebar'
import { StatsRow } from '@/components/app/StatsRow'
import { useRoute, type Route } from '@/hooks/useRoute'

/** The home view: stats, filters, trend, daily brief and the article feed. */
function Dashboard() {
  return (
    <div className="space-y-4">
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

/** Render the view that matches the current route. */
function RouteView({ route }: { route: Route }) {
  switch (route.name) {
    case 'article':
      return <Reader id={route.id} />
    case 'story':
      return <StoryPage id={route.id} />
    default:
      return <Dashboard />
  }
}

/** App shell with header, motion settings and the active route. */
export default function App() {
  const route = useRoute()
  if (route.name === 'landing') return <Landing />
  return (
    // Respect the OS "reduce motion" setting for every animation below.
    <MotionConfig reducedMotion="user">
      <div className="min-h-dvh">
        <Header />
        <main className="mx-auto max-w-[96rem] px-4 py-5 sm:px-6">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={route.name === 'home' ? 'home' : `${route.name}-${route.id}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              <RouteView route={route} />
            </motion.div>
          </AnimatePresence>
        </main>
        <footer className="border-t py-5 text-center text-xs text-muted-foreground">
          <strong className="text-foreground">SignalDesk</strong> · FastAPI + React · sentiment, topics &amp; summaries
          computed on ingest · <a href="#/welcome" className="underline-offset-2 hover:underline">About</a>
        </footer>
      </div>
    </MotionConfig>
  )
}
