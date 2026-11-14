// Landing page: explains SignalDesk and lets visitors enter the dashboard with "Try as a demo".
import { useState } from 'react'
import { ArrowRight, Eye, Flame, Gauge, Layers, Loader2, Mail, Play, RefreshCw, Zap, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ShimmerButton } from '@/components/ui/shimmer-button'
import { enterDashboard } from '@/hooks/useRoute'
import { startDemo } from '@/lib/api'

/** A capability shown in the feature grid. */
interface Feature {
  icon: LucideIcon
  title: string
  text: string
}

const FEATURES: Feature[] = [
  { icon: Layers, title: 'One story, many reports', text: 'Articles about the same event are grouped, with the most informative report on top.' },
  { icon: Gauge, title: 'Information score', text: 'Every article is scored on how much concrete detail it carries, not just clicks.' },
  { icon: Flame, title: 'Hot topics & sentiment', text: 'See what is trending and how each outlet frames it, from negative to positive.' },
  { icon: Eye, title: 'Watchlist alerts', text: 'Follow the terms, topics and outlets you care about and get one alert per story.' },
  { icon: Mail, title: 'Daily brief', text: 'A short digest of the day, ready to send to Slack or email.' },
  { icon: RefreshCw, title: 'Runs itself', text: 'Feeds are re-checked every 15 minutes, so the latest news is always in.' },
]

/** The public front door of the app. */
export function Landing() {
  const [starting, setStarting] = useState(false)

  /** Start a demo session, then open the dashboard. */
  const tryDemo = async () => {
    setStarting(true)
    const live = await startDemo()
    toast.success(live ? 'Demo started: you can run live ingests' : 'Welcome! This deployment is read-only')
    enterDashboard()
  }

  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-5">
        <span className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-4 fill-current" aria-hidden />
          </span>
          <span className="text-[15px] font-bold tracking-tight">SignalDesk</span>
        </span>
        <Button variant="ghost" size="sm" onClick={enterDashboard}>
          Browse read-only <ArrowRight data-icon="inline-end" />
        </Button>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-16">
        <section className="py-14 text-center sm:py-20">
          <p className="mb-4 text-sm font-medium text-ai">News intelligence, on autopilot</p>
          <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            Cut through the noise. See the story behind the headlines.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted-foreground text-pretty sm:text-lg">
            SignalDesk pulls in dozens of news feeds, groups reports about the same event, scores how informative each
            one is, and tracks sentiment and trends, all updated every 15 minutes.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <ShimmerButton
              onClick={() => void tryDemo()}
              disabled={starting}
              background="var(--primary)"
              shimmerColor="#ffffff"
              borderRadius="0.625rem"
              className="h-11 px-6 text-base font-medium disabled:opacity-70"
            >
              {starting ? <Loader2 className="mr-2 size-4 animate-spin" aria-hidden /> : <Play className="mr-2 size-4 fill-current" aria-hidden />}
              {starting ? 'Starting demo…' : 'Try as a demo'}
            </ShimmerButton>
            <Button variant="outline" size="lg" className="h-11 px-5" onClick={enterDashboard}>
              Just look around
            </Button>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">No sign-up. The demo lets you run live ingests for a couple of hours.</p>
        </section>

        <section aria-label="Features" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <Card key={title} className="gap-2 p-5">
              <Icon className="size-5 text-link" aria-hidden />
              <h2 className="text-[15px] font-semibold">{title}</h2>
              <p className="text-sm text-muted-foreground">{text}</p>
            </Card>
          ))}
        </section>

        <section className="mt-10 rounded-xl border bg-card/50 p-5 text-sm text-muted-foreground">
          <strong className="text-foreground">What the demo can do:</strong> browse and filter stories, open reports,
          compare outlets, and run a live ingest. Editing feeds, the watchlist and AI summaries stay locked so the shared
          demo stays tidy.
        </section>
      </main>

      <footer className="border-t py-5 text-center text-xs text-muted-foreground">
        <strong className="text-foreground">SignalDesk</strong> · FastAPI + React
      </footer>
    </div>
  )
}
