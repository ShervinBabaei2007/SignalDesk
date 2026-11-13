import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { ArticleFeed } from '@/components/app/ArticleFeed'
import { DailyBrief } from '@/components/app/DailyBrief'
import { Filters } from '@/components/app/Filters'
import { Header } from '@/components/app/Header'
import { Reader } from '@/components/app/Reader'
import { Sidebar } from '@/components/app/Sidebar'
import { StatsRow } from '@/components/app/StatsRow'
import { useRoute } from '@/hooks/useRoute'

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

export default function App() {
  const route = useRoute()
  return (
    // Respect the OS "reduce motion" setting for every animation below.
    <MotionConfig reducedMotion="user">
      <div className="min-h-dvh">
        <Header />
        <main className="mx-auto max-w-7xl px-4 py-5">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={route.name === 'article' ? `article-${route.id}` : 'home'}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {route.name === 'article' ? <Reader id={route.id} /> : <Dashboard />}
            </motion.div>
          </AnimatePresence>
        </main>
        <footer className="border-t py-5 text-center text-xs text-muted-foreground">
          <strong className="text-foreground">SignalDesk</strong> · FastAPI + React · sentiment, topics &amp; summaries
          computed on ingest
        </footer>
      </div>
    </MotionConfig>
  )
}
