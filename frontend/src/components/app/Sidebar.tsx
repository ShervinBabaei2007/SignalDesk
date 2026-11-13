import { useState, type ReactNode } from 'react'
import { Flame, Loader2, Mail, Sun } from 'lucide-react'
import { toast } from 'sonner'
import { BlurFade } from '@/components/ui/blur-fade'
import { BorderBeam } from '@/components/ui/border-beam'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ShimmerButton } from '@/components/ui/shimmer-button'
import { ToneIcon, toneText } from '@/components/app/Sentiment'
import { useDashboard } from '@/hooks/useDashboard'
import { api, ApiError, type DigestItem } from '@/lib/api'
import { TOPIC_EMOJI } from '@/lib/format'
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

function CategoryRow({
  label, icon, count, max, active, hint, onClick,
}: { label: string; icon: ReactNode; count: number; max: number; active: boolean; hint?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      title={hint}
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
        active && 'bg-accent font-medium',
      )}
    >
      <span className="flex flex-1 items-center gap-2">
        {icon} {label}
      </span>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <span className="block h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${(count / Math.max(max, 1)) * 100}%` }} />
      </span>
      <span className="w-7 text-right font-mono text-xs text-muted-foreground">{count}</span>
    </button>
  )
}

function Topics() {
  const { stats, filters, setFilter, hotCount } = useDashboard()
  const entries = Object.entries(stats?.topic_breakdown ?? {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(...entries.map(([, n]) => n), 1)
  return (
    <BlurFade delay={0.15} className="compact-hide">
      <Card>
        <CardHeader>
          <CardTitle className="text-[15px]">Topics</CardTitle>
          <CardDescription>Browse your feed by category.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-0.5">
          <CategoryRow
            label="Hot topics"
            icon={<Flame className="size-4 text-amber-500" aria-hidden />}
            count={hotCount}
            max={Math.max(max, hotCount)}
            active={filters.hot === '1'}
            hint="Stories many outlets are covering right now"
            onClick={() => setFilter({ hot: filters.hot === '1' ? '' : '1', topic: '' })}
          />
          {entries.map(([topic, n]) => (
            <CategoryRow
              key={topic}
              label={topic}
              icon={<span aria-hidden>{TOPIC_EMOJI[topic] ?? '📰'}</span>}
              count={n}
              max={max}
              active={filters.topic === topic}
              onClick={() => setFilter({ topic: filters.topic === topic ? '' : topic, hot: '' })}
            />
          ))}
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
