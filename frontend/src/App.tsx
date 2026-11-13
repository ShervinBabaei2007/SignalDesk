import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { ArticleFeed } from '@/components/app/ArticleFeed'
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
      <div className="grid items-start gap-5 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <div className="compact-hide sidebar-scroll order-2 lg:sticky lg:top-[4.5rem] lg:order-1 lg:max-h-[calc(100dvh-5.5rem)] lg:overflow-y-auto lg:pr-1">
          <Sidebar />
        </div>
        <div className="order-1 min-w-0 lg:order-2 lg:[html[data-compact=on]_&]:col-span-2">
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
