import { useState } from 'react'
import { Loader2, Mail, Sun } from 'lucide-react'
import { toast } from 'sonner'
import { BlurFade } from '@/components/ui/blur-fade'
import { BorderBeam } from '@/components/ui/border-beam'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ToneIcon, toneText } from '@/components/app/Sentiment'
import { useDashboard } from '@/hooks/useDashboard'
import { api, ApiError, type DigestItem } from '@/lib/api'
import { describeSentiment } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

function DigestGroup({ title, items, tone }: { title: string; items: DigestItem[]; tone: 'positive' | 'negative' }) {
  if (!items.length) return null
  return (
    <div className="min-w-0 space-y-1.5">
      <div className={cn('flex items-center gap-1 text-[11px] font-semibold tracking-wider uppercase', toneText[tone])}>
        <ToneIcon tone={tone} />
        {title}
      </div>
      {items.map((item, i) => {
        const level = describeSentiment(item.sentiment)
        return (
          <a
            key={item.id}
            href={`#/article/${item.id}`}
            className={cn(i > 0 ? 'hidden md:block' : 'block', 'rounded-lg border bg-background/60 px-3 py-2 text-[13px] leading-snug transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none')}
          >
            <span className={cn('mb-0.5 block text-[11px] font-semibold', toneText[tone])} title={`Score ${level.score} (−1 to +1)`}>
              {level.label}
            </span>
            <span className="line-clamp-2">{item.title}</span>
          </a>
        )
      })}
    </div>
  )
}

/** Today at a glance: the one-line headline plus the most positive and negative stories. */
export function DailyBrief() {
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
    <BlurFade delay={0.1} className="compact-hide">
      <Card className="relative mb-4 overflow-hidden">
        <BorderBeam size={140} duration={10} colorFrom="var(--ai)" colorTo="var(--link)" />
        <CardContent className="grid gap-5 md:grid-cols-[1.1fr_1fr_1fr]">
          <div className="flex flex-col justify-between gap-3">
            <div className="space-y-2">
              <h2 className="flex items-center gap-2 text-[15px] font-semibold">
                <Sun className="size-4 text-ai" aria-hidden /> Daily Brief
              </h2>
              {digest ? (
                <p className="text-sm leading-relaxed text-muted-foreground">{digest.headline}</p>
              ) : (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-4/5" />
                </div>
              )}
            </div>
            <Button variant="outline" size="sm" className="w-fit" onClick={send} disabled={sending}>
              {sending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Mail data-icon="inline-start" />}
              Send brief
            </Button>
          </div>
          {digest ? (
            <>
              <DigestGroup title="Most positive" items={digest.top_positive.slice(0, 2)} tone="positive" />
              <DigestGroup title="Most negative" items={digest.top_negative.slice(0, 2)} tone="negative" />
            </>
          ) : (
            <>
              <Skeleton className="h-28 rounded-lg" />
              <Skeleton className="h-28 rounded-lg" />
            </>
          )}
        </CardContent>
      </Card>
    </BlurFade>
  )
}
