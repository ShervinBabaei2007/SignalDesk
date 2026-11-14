// Landing page: explains SignalDesk and lets visitors open their own private workspace or take the demo tour.
import { useEffect, useState } from 'react'
import { ArrowRight, Compass, Eye, Flame, Gauge, Layers, LockKeyhole, Mail, Play, RefreshCw, Zap, type LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ShimmerButton } from '@/components/ui/shimmer-button'
import { getAuthStatus, type AuthStatus } from '@/lib/api'
import { enterDashboard, navigateAbsolute } from '@/lib/nav'

/** A capability shown in the feature grid. */
interface Feature {
  icon: LucideIcon
  title: string
  text: string
}

/** The capabilities highlighted on the landing page. */
const FEATURES: Feature[] = [
  { icon: Layers, title: 'One story, many reports', text: 'Articles about the same event are grouped, with the most informative report on top.' },
  { icon: Gauge, title: 'Information score', text: 'Every article is scored on how much concrete detail it carries, not just clicks.' },
  { icon: Flame, title: 'Hot topics & sentiment', text: 'See what is trending and how each outlet frames it, from negative to positive.' },
  { icon: Eye, title: 'Watchlist alerts', text: 'Follow the terms, topics and outlets you care about and get one alert per story.' },
  { icon: Mail, title: 'Daily brief', text: 'A short digest of the day, ready to copy and share.' },
  { icon: RefreshCw, title: 'Runs itself', text: 'Feeds are re-checked every hour, so the latest news is always in.' },
]

/** Public landing page that explains the app and sends visitors to /workspace or /demo. */
export function Landing() {
  const [status, setStatus] = useState<AuthStatus | null>(null)

  // Ask the server once whether private workspaces are enabled, which decides the entry buttons.
  useEffect(() => {
    void getAuthStatus().then(setStatus)
  }, [])

  const workspaces = status?.workspaces ?? false
  // The highlighted button opens a workspace when the server allows it, and the demo otherwise.
  const primaryIcon = workspaces ? <LockKeyhole className="mr-2 size-4" aria-hidden /> : <Play className="mr-2 size-4 fill-current" aria-hidden />
  const primaryLabel = workspaces ? 'Open my workspace' : 'Try as a demo'

  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
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

      <main className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <section className="pt-12 pb-10 text-center sm:pt-20 sm:pb-14">
          <p className="mb-5 text-sm font-semibold tracking-wide text-ai uppercase">News intelligence, on autopilot</p>
          <h1 className="mx-auto max-w-4xl text-[2.15rem] leading-[1.1] font-bold tracking-tight text-balance sm:text-5xl lg:text-6xl">
            Cut through the noise. See the story behind the headlines.
          </h1>
          <p className="mx-auto mt-6 max-w-3xl text-base leading-relaxed text-muted-foreground text-pretty sm:text-lg lg:text-xl">
            SignalDesk pulls in dozens of news feeds, groups reports about the same event, scores how informative each
            one is, and tracks sentiment and trends, all refreshed every hour.
          </p>
          <div className="mx-auto mt-9 flex w-full max-w-xs flex-col items-center justify-center gap-3 sm:max-w-none sm:flex-row">
            <ShimmerButton
              onClick={() => navigateAbsolute(workspaces ? '/workspace' : '/demo')}
              background="var(--primary)"
              shimmerColor="#ffffff"
              borderRadius="0.625rem"
              className="h-11 w-full px-6 text-base font-medium sm:w-auto"
            >
              {primaryIcon}
              {primaryLabel}
            </ShimmerButton>
            {workspaces ? (
              <Button variant="outline" size="lg" className="h-11 w-full px-5 sm:w-auto" onClick={() => navigateAbsolute('/demo')}>
                <Compass data-icon="inline-start" />
                Take the demo tour
              </Button>
            ) : (
              <Button variant="outline" size="lg" className="h-11 w-full px-5 sm:w-auto" onClick={enterDashboard}>
                Just look around
              </Button>
            )}
          </div>
          <p className="mt-4 text-[13px] text-muted-foreground">
            {workspaces
              ? `No sign-up. Your workspace is private to you and deleted automatically after ${status?.workspace_ttl_days ?? 7} days.`
              : 'No sign-up. The demo lets you run live ingests for a couple of hours.'}
          </p>

          <figure className="relative mx-auto mt-14 max-w-5xl sm:mt-16">
            <div aria-hidden className="absolute inset-x-6 -top-6 h-40 rounded-full bg-primary/25 blur-3xl sm:inset-x-12" />
            {/* a phone-sized capture on small screens (the desktop one would shrink to an unreadable strip) */}
            <img
              src="/screenshots/mobile.png"
              alt="SignalDesk on a phone: the story feed with lead images, summaries and source links"
              width={392}
              height={845}
              className="relative mx-auto w-full max-w-[300px] rounded-3xl border border-foreground/10 shadow-2xl ring-1 ring-foreground/5 sm:hidden"
            />
            <img
              src="/screenshots/dashboard.png"
              alt="The SignalDesk dashboard: key figures, a seven-day sentiment trend, topics and the story feed with lead images"
              width={1388}
              height={868}
              className="relative hidden w-full rounded-2xl border border-foreground/10 shadow-2xl ring-1 ring-foreground/5 sm:block"
            />
          </figure>
        </section>

        <section aria-label="Features" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <Card key={title} className="gap-2 p-5">
              <Icon className="size-5 text-link" aria-hidden />
              <h2 className="text-base font-semibold">{title}</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">{text}</p>
            </Card>
          ))}
        </section>

        {workspaces ? (
          <section aria-label="Ways to explore" className="mt-10 grid gap-4 sm:grid-cols-2">
            <Card className="gap-2 p-5">
              <LockKeyhole className="size-5 text-link" aria-hidden />
              <h2 className="text-[15px] font-semibold">Your workspace</h2>
              <p className="text-sm text-muted-foreground">
                The full application, just for you. Add your own feeds, build a watchlist, run ingests and summarize
                articles. Nothing you change is visible to anyone else, and the shared news stays available alongside it.
              </p>
            </Card>
            <Card className="gap-2 p-5">
              <Compass className="size-5 text-link" aria-hidden />
              <h2 className="text-[15px] font-semibold">Demo tour</h2>
              <p className="text-sm text-muted-foreground">
                A quick look at the shared data: browse and filter stories, open reports, compare outlets and run a live
                ingest. Nothing to set up, and nothing you can change.
              </p>
            </Card>
          </section>
        ) : (
          <section className="mt-10 rounded-xl border bg-card/50 p-5 text-sm text-muted-foreground">
            <strong className="text-foreground">What the demo can do:</strong> browse and filter stories, open reports,
            compare outlets, and run a live ingest. Editing feeds, the watchlist and AI summaries stay locked so the shared
            demo stays tidy.
          </section>
        )}
      </main>

      <footer className="border-t py-5 text-center text-xs text-muted-foreground">
        <strong className="text-foreground">SignalDesk</strong> · FastAPI + React
      </footer>
    </div>
  )
}
