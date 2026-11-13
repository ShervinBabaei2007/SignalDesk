import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ExternalLink, Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { AlsoCoveredBy } from '@/components/app/AlsoCoveredBy'
import { SentimentBadge, SentimentInfo, SentimentScale, toneBg, toneText } from '@/components/app/Sentiment'
import { Badge } from '@/components/ui/badge'
import { BlurFade } from '@/components/ui/blur-fade'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type ArticleDetail } from '@/lib/api'
import { domainOf, keywordList, timeAgo, TOPIC_EMOJI } from '@/lib/format'
import { describeSentiment } from '@/lib/sentiment'
import { parseStructured } from '@/lib/structured'
import { cn } from '@/lib/utils'

function Hero({ article }: { article: ArticleDetail }) {
  const [failed, setFailed] = useState(false)
  if (!article.image_url || article.is_seed || failed) return null
  const domain = domainOf(article.url)
  return (
    <figure className="mb-5">
      <img
        src={article.image_url}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className="aspect-video w-full rounded-xl border bg-muted object-cover"
      />
      <figcaption className="mt-1.5 text-xs text-muted-foreground">
        Image from {domain} ·{' '}
        <a href={article.url} target="_blank" rel="noopener" className="text-link underline underline-offset-2">
          verify at the source ↗
        </a>
      </figcaption>
    </figure>
  )
}

function ReaderSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <Skeleton className="aspect-video w-full" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-8 w-4/5" />
        <Skeleton className="h-24 w-full" />
      </CardContent>
    </Card>
  )
}

export function Reader({ id }: { id: number }) {
  const [article, setArticle] = useState<ArticleDetail | null>(null)
  const [error, setError] = useState('')
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    setArticle(null)
    setError('')
    window.scrollTo({ top: 0 })
    let live = true
    api.article(id).then(
      (a) => live && setArticle(a),
      (e: Error) => live && setError(e.message),
    )
    return () => {
      live = false
    }
  }, [id])

  const sections = useMemo(
    () => parseStructured(article?.summary_structured ?? null, !!article?.summary_deep),
    [article],
  )

  const generate = async () => {
    setGenerating(true)
    try {
      setArticle(await api.summarize(id))
    } catch (err) {
      toast.error(`Could not generate summary: ${(err as Error).message}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Button variant="ghost" className="mb-3 -ml-2" render={<a href="#/" />}>
        <ArrowLeft data-icon="inline-start" /> Back to feed
      </Button>

      {error ? (
        <Card className="py-12 text-center">
          <h2 className="text-lg font-semibold">Article not found</h2>
          <p className="text-sm text-muted-foreground">{error}</p>
        </Card>
      ) : !article ? (
        <ReaderSkeleton />
      ) : (
        <Card className="gap-0 py-0">
          <CardContent className="p-5 sm:p-7">
            <Hero article={article} />

            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-muted-foreground">
              <span className="text-base" aria-hidden>{TOPIC_EMOJI[article.topic] ?? '📰'}</span>
              <span className="font-semibold text-link">{article.source}</span>
              <span>·</span>
              <span>{timeAgo(article.published_at)}</span>
              <SentimentBadge score={article.sentiment} />
              {article.analysis_source === 'llm' && (
                <Badge variant="secondary" className="gap-1 text-ai"><Sparkles className="size-3" /> AI analysis</Badge>
              )}
            </div>

            <h1 className="mt-3 text-2xl leading-tight font-bold tracking-tight sm:text-3xl">{article.title}</h1>

            <BlurFade delay={0.05}>
              <div className="mt-5 rounded-xl border border-ai/35 bg-ai/8 p-4">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-ai uppercase">
                    <Sparkles className="size-3.5" aria-hidden /> Straightforward summary
                  </span>
                  {!article.summary_deep && (
                    <Button size="sm" variant="outline" onClick={() => void generate()} disabled={generating}>
                      {generating ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Sparkles data-icon="inline-start" />}
                      Generate clean summary
                    </Button>
                  )}
                </div>
                <p className="text-[15px] leading-relaxed">
                  {article.summary_deep || article.summary || 'No summary available yet.'}
                </p>
              </div>
            </BlurFade>

            {sections.length > 1 && (
              <nav aria-label="Sections" className="mt-4 flex flex-wrap gap-1.5">
                {sections.map((s) => (
                  <Button key={s.id} variant="outline" size="sm" onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                    {s.title}
                  </Button>
                ))}
              </nav>
            )}

            <div className="mt-4 space-y-3">
              {sections.length ? (
                sections.map((s, i) => (
                  <BlurFade key={s.id} delay={0.05 * i} inView>
                    <section id={s.id} className="scroll-mt-20 rounded-xl border bg-muted/30 p-4">
                      <h2 className="mb-2 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">{s.title}</h2>
                      {s.bullets.length > 0 && (
                        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed marker:text-ai">
                          {s.bullets.map((b, j) => <li key={j}>{b}</li>)}
                        </ul>
                      )}
                      {s.paras.map((p, j) => <p key={j} className="mt-1.5 text-sm leading-relaxed">{p}</p>)}
                    </section>
                  </BlurFade>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No brief generated yet. Use the button above to create one.</p>
              )}
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5">
              {keywordList(article.keywords).map((k) => <Badge key={k} variant="secondary" className="font-normal">{k}</Badge>)}
            </div>

            {article.related.length > 0 && (
              <div className="mt-6">
                <AlsoCoveredBy items={article.related} />
              </div>
            )}

            <SentimentPanel score={article.sentiment} />

            {!article.is_seed && (
              <Button size="lg" className="mt-5 h-10" render={<a href={article.url} target="_blank" rel="noopener" />}>
                <ExternalLink data-icon="inline-end" /> Read the original article
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function SentimentPanel({ score }: { score: number }) {
  const d = describeSentiment(score)
  return (
    <div className="mt-6 rounded-xl border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1 text-sm font-medium">
          How positive or negative are the words? <SentimentInfo />
        </div>
        <span className={cn('rounded-full border px-2.5 py-0.5 text-xs font-semibold', toneBg[d.tone], toneText[d.tone])}>
          {d.label} · {d.score}
        </span>
      </div>
      <SentimentScale score={score} />
      <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">
        {d.blurb} This is about the words used, not whether the news is good or bad.
      </p>
    </div>
  )
}
