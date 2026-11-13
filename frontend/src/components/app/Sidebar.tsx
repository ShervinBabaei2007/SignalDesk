import { useState } from 'react'
import { Flame, Loader2, Mail, Sun } from 'lucide-react'
import { toast } from 'sonner'
import { BlurFade } from '@/components/ui/blur-fade'
import { BorderBeam } from '@/components/ui/border-beam'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { ShimmerButton } from '@/components/ui/shimmer-button'
import { ToneIcon, toneText } from '@/components/app/Sentiment'
import { useDashboard } from '@/hooks/useDashboard'
import { api, ApiError, type DigestItem } from '@/lib/api'
import { timeAgo, TOPIC_EMOJI } from '@/lib/format'
import { describeSentiment } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

function DigestGroup({ title, items, tone }: { title: string; items: DigestItem[]; tone: 'positive' | 'negative' }) {
  if (!items.length) return null
  return (
    <div className="space-y-1.5">
      <div className={cn('flex items-center gap-1 text-[11px] font-semibold tracking-wider uppercase', toneText[tone])}>
        <ToneIcon tone={tone} />
        {title}
      </div>
      {items.map((item) => (
        <a
          key={item.id}
          href={`#/article/${item.id}`}
          className="block rounded-lg border bg-background/60 px-3 py-2 text-[13px] leading-snug transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <span className={cn('mb-0.5 block text-[11px] font-semibold', toneText[tone])} title={`Score ${describeSentiment(item.sentiment).score} (−1 to +1)`}>
            {describeSentiment(item.sentiment).label}
          </span>
          {item.title.length > 70 ? `${item.title.slice(0, 70)}…` : item.title}
        </a>
      ))}
    </div>
  )
}

function DailyBrief() {
  const { digest } = useDashboard()
  const [sending, setSending] = useState(false)

  const send = async () => {
    setSending(true)
    try {
      const r = await api.sendDigest()
      toast.success(`Daily brief sent via ${r.sent.join(' + ')}`)
    } catch (err) {
      const e = err as ApiError
      toast.error(
        e.status === 400
          ? 'No delivery channel configured — set Slack or SMTP settings'
          : e.status === 401
            ? 'Add your API token in Settings first'
            : `Could not send brief: ${e.message}`,
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <BlurFade delay={0.15}>
      <Card className="relative overflow-hidden">
        <BorderBeam size={120} duration={9} colorFrom="var(--ai)" colorTo="var(--link)" />
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-[15px]">
            <Sun className="size-4 text-ai" aria-hidden /> Daily Brief
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {digest ? (
            <>
              <p className="text-sm leading-relaxed">{digest.headline}</p>
              <DigestGroup title="Most positive" items={digest.top_positive.slice(0, 2)} tone="positive" />
              <DigestGroup title="Most negative" items={digest.top_negative.slice(0, 2)} tone="negative" />
            </>
          ) : (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-4/5" />
            </div>
          )}
          <Button variant="outline" className="w-full" onClick={send} disabled={sending}>
            {sending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Mail data-icon="inline-start" />}
            Send brief
          </Button>
        </CardContent>
      </Card>
    </BlurFade>
  )
}

function HotTopics() {
  const { trending, openStory, filters } = useDashboard()
  return (
    <section aria-labelledby="hot-topics">
      <h3 id="hot-topics" className="mb-1.5 flex items-center gap-1.5 text-[13px] font-semibold">
        <Flame className="size-4 text-amber-500" aria-hidden /> Hot topics
        <span className="font-normal text-muted-foreground">· most covered right now</span>
      </h3>
      {trending.length === 0 ? (
        <p className="py-2 text-[13px] text-muted-foreground">No big stories yet. Run an ingest to find out what everyone is covering.</p>
      ) : (
        <ol className="space-y-0.5">
          {trending.map((t, i) => {
            const active = filters.cluster === String(t.cluster_id)
            const tone = describeSentiment(t.avg_sentiment).tone
            return (
              <li key={t.cluster_id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    openStory(t.cluster_id)
                    window.scrollTo({ top: 0, behavior: 'smooth' })
                  }}
                  className={cn(
                    'group flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
                    active && 'bg-accent',
                  )}
                >
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-md bg-muted text-[11px] font-semibold text-muted-foreground tabular-nums">
                    {i + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-[13px] leading-snug font-medium group-hover:text-link">{t.title}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[11px] text-muted-foreground">
                      <span className="font-medium text-foreground/80">{t.outlets} outlets</span>
                      <span>·</span>
                      <span>{t.reports} reports</span>
                      <span>·</span>
                      <span>{timeAgo(t.latest_at)}</span>
                      <span className={cn('inline-flex items-center gap-0.5', toneText[tone])} title={`${describeSentiment(t.avg_sentiment).label} wording`}>
                        <ToneIcon tone={tone} className="size-2.5" />
                      </span>
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

function Topics() {
  const { stats, filters, setFilter } = useDashboard()
  const entries = Object.entries(stats?.topic_breakdown ?? {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(...entries.map(([, n]) => n), 1)
  return (
    <BlurFade delay={0.15} className="compact-hide">
      <Card>
        <CardHeader>
          <CardTitle className="text-[15px]">Topics</CardTitle>
          <CardDescription>What the world is talking about, and how your feed breaks down.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <HotTopics />
          <Separator />
          <section aria-labelledby="by-category">
            <h3 id="by-category" className="mb-1.5 text-[13px] font-semibold">By category</h3>
            <div className="space-y-0.5">
              {entries.map(([topic, n]) => {
                const active = filters.topic === topic
                return (
                  <button
                    key={topic}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setFilter({ topic: active ? '' : topic })}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
                      active && 'bg-accent font-medium',
                    )}
                  >
                    <span className="flex-1">
                      {TOPIC_EMOJI[topic] ?? '📰'} {topic}
                    </span>
                    <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                      <span className="block h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${(n / max) * 100}%` }} />
                    </span>
                    <span className="w-7 text-right font-mono text-xs text-muted-foreground">{n}</span>
                  </button>
                )
              })}
            </div>
          </section>
        </CardContent>
      </Card>
    </BlurFade>
  )
}

function SentimentSplit() {
  const { stats } = useDashboard()
  if (!stats) return null
  const total = Math.max(stats.positive + stats.neutral + stats.negative, 1)
  const rows = [
    { label: 'Positive', n: stats.positive, dot: 'bg-positive' },
    { label: 'Neutral', n: stats.neutral, dot: 'bg-neutral' },
    { label: 'Negative', n: stats.negative, dot: 'bg-negative' },
  ]
  return (
    <BlurFade delay={0.2} className="compact-hide">
      <Card>
        <CardHeader>
          <CardTitle className="text-[15px]">Sentiment split</CardTitle>
          <CardDescription>How the words in your articles lean.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <span className={cn('size-2.5 rounded-full', r.dot)} />
                {r.label}
              </span>
              <span className="font-mono text-xs text-muted-foreground">
                {r.n} · {Math.round((r.n / total) * 100)}%
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </BlurFade>
  )
}

function IngestCard() {
  const { ingesting, ingestResult, runIngest, feeds } = useDashboard()
  return (
    <BlurFade delay={0.25} className="compact-hide">
      <Card>
        <CardHeader>
          <CardTitle className="text-[15px]">Pull the latest news</CardTitle>
          <CardDescription>
            Fetches all {feeds.filter((f) => f.is_active).length || ''} active feeds, removes duplicates and analyzes new
            articles. Runs automatically every 30 minutes too.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ShimmerButton
            onClick={() => void runIngest()}
            disabled={ingesting}
            className="h-9 w-full text-sm font-medium disabled:opacity-70"
            background="var(--primary)"
            shimmerColor="#ffffff"
          >
            {ingesting ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" /> Checking feeds…
              </>
            ) : (
              'Run ingestion'
            )}
          </ShimmerButton>
          {ingestResult && (
            <p className="text-xs leading-relaxed text-muted-foreground" aria-live="polite">
              {ingestResult}
            </p>
          )}
        </CardContent>
      </Card>
    </BlurFade>
  )
}

export function Sidebar() {
  return (
    <aside className="space-y-3">
      <Topics />
      <DailyBrief />
      <SentimentSplit />
      <IngestCard />
    </aside>
  )
}
