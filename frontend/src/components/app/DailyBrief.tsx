// Card showing the daily brief with its top positive and negative stories and a send button.
import { useState } from 'react'
import { Copy, Download, Loader2, Mail, Sun } from 'lucide-react'
import { toast } from 'sonner'
import { BlurFade } from '@/components/ui/blur-fade'
import { BorderBeam } from '@/components/ui/border-beam'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { AppLink as Link } from '@/components/app/AppLink'
import { LockMark } from '@/components/app/LockedDialog'
import { ToneIcon, toneText } from '@/components/app/Sentiment'
import { useDashboard } from '@/hooks/useDashboard'
import { useMode } from '@/hooks/useMode'
import { useSettings } from '@/hooks/useSettings'
import { api, ApiError, authMessage, type Digest, type DigestItem } from '@/lib/api'
import { copyBrief, downloadBrief } from '@/lib/briefActions'
import { openLocked } from '@/lib/nav'
import { describeSentiment } from '@/lib/sentiment'
import { cn } from '@/lib/utils'

/** A titled list of digest items in one tone. */
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
        // On small screens only the first story is shown to keep the card short.
        return (
          <Link
            key={item.id}
            to={`/article/${item.id}`}
            className={cn(i > 0 ? 'hidden md:block' : 'block', 'rounded-lg border bg-background/60 px-3 py-2 text-[13px] leading-snug transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none')}
          >
            <span className={cn('mb-0.5 block text-[11px] font-semibold', toneText[tone])} title={`Score ${level.score} (−1 to +1)`}>
              {level.label}
            </span>
            <span className="line-clamp-2">{item.title}</span>
          </Link>
        )
      })}
    </div>
  )
}

/** Friendly message for a failed brief send. */
function sendErrorMessage(e: ApiError, token: string): string {
  if (e.status === 400) return 'No delivery channel configured — set Slack or SMTP settings'
  if (e.status === 401) return authMessage(token)
  return `Could not send brief: ${e.message}`
}

/** The brief's buttons: locked in the demo, copy and download in a workspace, send otherwise. */
function BriefActions({ digest }: { digest: Digest | null }) {
  const { token } = useSettings()
  const { mode, locked } = useMode()
  const [sending, setSending] = useState(false)

  /** Delivers the brief through the configured channels and reports the outcome in a toast. */
  const send = async () => {
    setSending(true)
    try {
      const r = await api.sendDigest()
      toast.success(`Daily brief sent via ${r.sent.join(' + ')}`)
    } catch (err) {
      toast.error(sendErrorMessage(err as ApiError, token))
    } finally {
      setSending(false)
    }
  }

  if (locked('brief')) {
    return (
      <Button variant="outline" size="sm" className="w-fit" onClick={() => openLocked('brief')}>
        <Copy data-icon="inline-start" /> Copy brief <LockMark feature="brief" />
      </Button>
    )
  }
  if (mode === 'workspace') {
    // A workspace has no delivery channel of its own, so it shares the brief as text.
    return (
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => void copyBrief(digest)} disabled={!digest}>
          <Copy data-icon="inline-start" /> Copy brief
        </Button>
        <Button variant="ghost" size="sm" onClick={() => downloadBrief(digest)} disabled={!digest}>
          <Download data-icon="inline-start" /> Download
        </Button>
      </div>
    )
  }
  return (
    <Button variant="outline" size="sm" className="w-fit" onClick={send} disabled={sending}>
      {sending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Mail data-icon="inline-start" />}
      Send brief
    </Button>
  )
}

/** Today at a glance: the one-line headline plus the most positive and negative stories. */
export function DailyBrief() {
  const { digest } = useDashboard()

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
            <BriefActions digest={digest} />
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
