import { Award, ChevronLeft, ChevronRight, ExternalLink, FileText, Link2, Newspaper, Satellite, Sparkles, Sprout, Star, X } from 'lucide-react'
import { useRef } from 'react'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { BlurFade } from '@/components/ui/blur-fade'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem } from '@/components/ui/pagination'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { HotStories } from '@/components/app/HotStories'
import { InfoScore } from '@/components/app/InfoScore'
import { StoryReports } from '@/components/app/StoryReports'
import { SentimentBadge } from '@/components/app/Sentiment'
import { PAGE_SIZE, useDashboard } from '@/hooks/useDashboard'
import { useSettings } from '@/hooks/useSettings'
import type { Article, Story } from '@/lib/api'
import { domainOf, keywordList, timeAgo, TOPIC_EMOJI } from '@/lib/format'
import { pageWindow } from '@/lib/pagination'

function StoryChip({ article }: { article: Article }) {
  const { openStory } = useDashboard()
  const sources = article.cluster_sources
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              openStory(article.cluster_id!)
              window.scrollTo({ top: 0, behavior: 'smooth' })
            }}
            className="inline-flex h-5 items-center gap-1 rounded-full border border-link/40 px-2 text-xs font-semibold text-link transition-colors hover:bg-link/10 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          />
        }
      >
        <Newspaper className="size-3" aria-hidden />
        {article.cluster_size} reports · {sources.length} source{sources.length === 1 ? '' : 's'}
      </TooltipTrigger>
      <TooltipContent className="max-w-64">Also reported by {sources.join(', ')}. Click to see all coverage.</TooltipContent>
    </Tooltip>
  )
}

function ArticleCard({
  article: a, index, story, defaultOpen = false,
}: { article: Article; index: number; story?: Story; defaultOpen?: boolean }) {
  const summary = a.summary_deep || a.summary
  const domain = a.is_seed ? '' : domainOf(a.url)
  const open = () => {
    location.hash = `#/article/${a.id}`
  }
  return (
    <BlurFade delay={Math.min(index, 8) * 0.04} duration={0.3} offset={8}>
      <Card
        onClick={open}
        className="cursor-pointer gap-0 py-0 transition-colors hover:bg-card/80 hover:ring-foreground/20"
      >
        <CardContent className="space-y-2.5 p-4">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-muted-foreground">
            <span className="font-semibold text-link">{a.source}</span>
            {domain && (
              <span className="inline-flex items-center gap-1" title="The story’s real address">
                <Link2 className="size-3" aria-hidden />
                {domain}
              </span>
            )}
            <span>·</span>
            <span>{timeAgo(a.published_at)}</span>
            <SentimentBadge score={a.sentiment} />
            {a.importance ? (
              <Badge variant="secondary" className="gap-1" title="Model importance score (1–10)">
                <Star className="size-3" aria-hidden />
                {a.importance.toFixed(0)}/10
              </Badge>
            ) : null}
            {a.summary_deep && (
              <Badge variant="secondary" className="compact-hide gap-1 text-ai" title="Summary generated from the full article page">
                <Sparkles className="size-3" aria-hidden />
                deep
              </Badge>
            )}
            <InfoScore score={a.info_score} />
            {story ? (
              story.report_count > 1 && (
                <Badge variant="outline" className="gap-1 border-link/40 font-semibold text-link" title="The most informative of this story's reports">
                  <Award className="size-3" aria-hidden />
                  Best of {story.report_count} reports · {story.outlets} {story.outlets === 1 ? 'outlet' : 'outlets'}
                </Badge>
              )
            ) : (
              a.cluster_size > 1 && <StoryChip article={a} />
            )}
          </div>

          <h3 className="text-[15.5px] leading-snug font-semibold tracking-tight">
            <a href={`#/article/${a.id}`} onClick={(e) => e.stopPropagation()} className="hover:text-link">
              {a.title}
            </a>
          </h3>

          {summary && <p className="line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">{summary}</p>}
          {a.why_it_matters && (
            <p className="rounded-md border-l-2 border-ai bg-ai/8 px-3 py-1.5 text-[13px] leading-relaxed">
              <span className="mr-1.5 text-[11px] font-semibold tracking-wide text-ai uppercase">Why it matters</span>
              {a.why_it_matters}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="compact-hide flex flex-wrap gap-1.5">
              <Badge variant="outline">
                {TOPIC_EMOJI[a.topic] ?? '📰'} {a.topic}
              </Badge>
              {keywordList(a.keywords, 4).map((k) => (
                <Badge key={k} variant="secondary" className="font-normal">
                  {k}
                </Badge>
              ))}
            </div>
            <div className="ml-auto flex gap-2">
              <Button variant="outline" size="sm" onClick={open}>
                <FileText data-icon="inline-start" />
                Summary
              </Button>
              {a.is_seed ? (
                <Badge variant="secondary" className="h-7 gap-1 px-2.5" title="Demo article — placeholder content, no external page">
                  <Sprout className="size-3" aria-hidden />
                  Demo
                </Badge>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  render={<a href={a.url} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()} />}
                >
                  <ExternalLink data-icon="inline-end" />
                  Visit
                </Button>
              )}
            </div>
          </div>
          {story && <StoryReports others={story.others} defaultOpen={defaultOpen} clusterId={story.cluster_id} />}
        </CardContent>
      </Card>
    </BlurFade>
  )
}

function FeedSkeleton() {
  return (
    <div className="space-y-2.5" aria-hidden>
      {Array.from({ length: 5 }).map((_, i) => (
        <Card key={i} className="gap-0 py-0">
          <CardContent className="space-y-3 p-4">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-6 w-1/3 rounded-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function FeedPagination({ onNavigate, noun }: { onNavigate: () => void; noun: string }) {
  const { page, pageCount, setPage, total } = useDashboard()
  if (pageCount <= 1) return null
  const go = (p: number) => {
    setPage(p)
    onNavigate()
  }
  const from = (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)
  return (
    <div className="mt-5 space-y-2">
      <Pagination aria-label="Article pages">
        <PaginationContent className="flex-wrap justify-center gap-1">
          <PaginationItem>
            <Button variant="ghost" size="sm" disabled={page === 1} onClick={() => go(page - 1)} aria-label="Previous page">
              <ChevronLeft data-icon="inline-start" />
              <span className="hidden sm:inline">Previous</span>
            </Button>
          </PaginationItem>
          {pageWindow(page, pageCount).map((item, i) =>
            item === 'gap' ? (
              <PaginationItem key={`gap-${i}`}>
                <PaginationEllipsis />
              </PaginationItem>
            ) : (
              <PaginationItem key={item}>
                <Button
                  variant={item === page ? 'default' : 'ghost'}
                  size="icon"
                  aria-label={`Page ${item}`}
                  aria-current={item === page ? 'page' : undefined}
                  onClick={() => go(item)}
                  className="tabular-nums"
                >
                  {item}
                </Button>
              </PaginationItem>
            ),
          )}
          <PaginationItem>
            <Button variant="ghost" size="sm" disabled={page === pageCount} onClick={() => go(page + 1)} aria-label="Next page">
              <span className="hidden sm:inline">Next</span>
              <ChevronRight data-icon="inline-end" />
            </Button>
          </PaginationItem>
        </PaginationContent>
      </Pagination>
      <p className="text-center text-xs text-muted-foreground">
        Page {page} of {pageCount} · showing {from}–{to} of {total} {noun}
      </p>
    </div>
  )
}

export function ArticleFeed() {
  const {
    stories, articles, grouped, total, articleTotal, loading, filters, setFilter, clearFilters, hasActiveFilters,
  } = useDashboard()
  const { setGrouped } = useSettings()
  const count = grouped ? stories.length : articles.length
  const sources = filters.cluster
    ? [...new Set(grouped ? stories.flatMap((s) => s.sources) : articles.map((a) => a.source))]
    : []
  const top = useRef<HTMLElement>(null)
  const toTop = () => top.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <section ref={top} aria-labelledby="feed-title" className="scroll-mt-20">
      <div className="mb-3 flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <h2 id="feed-title" className="text-lg font-semibold tracking-tight">
          Signal Feed
        </h2>
        <span className="text-sm text-muted-foreground">
          {grouped
            ? `${total} ${total === 1 ? 'story' : 'stories'} · ${articleTotal} ${articleTotal === 1 ? 'article' : 'articles'}`
            : `${total} ${total === 1 ? 'article' : 'articles'}`}
        </span>
        <div className="ml-auto flex items-center gap-2" title="Combine reports of the same event into one card, best-informed report first">
          <Switch id="group-stories" checked={grouped} onCheckedChange={setGrouped} />
          <Label htmlFor="group-stories" className="text-sm font-normal">
            Group same story
          </Label>
        </div>
      </div>
      {filters.hot && !filters.cluster && <HotStories />}

      {filters.cluster && (
        <Alert className="mb-3">
          <Newspaper />
          <AlertDescription className="text-foreground">
            One story, {articleTotal} reports{sources.length ? ` from ${sources.join(', ')}` : ''}
          </AlertDescription>
          <AlertAction>
            <Button variant="ghost" size="sm" onClick={() => setFilter({ cluster: '' })}>
              <X data-icon="inline-start" />
              Show all
            </Button>
          </AlertAction>
        </Alert>
      )}

      {loading && count === 0 ? (
        <FeedSkeleton />
      ) : count === 0 ? (
        <Card className="items-center py-14 text-center">
          <Satellite className="size-9 text-muted-foreground" aria-hidden />
          <h3 className="text-base font-semibold">No signals found</h3>
          <p className="max-w-xs text-sm text-muted-foreground">
            Nothing matches these filters. Try a different search, or run an ingest to pull in fresh articles.
          </p>
          {hasActiveFilters && (
            <Button variant="outline" onClick={clearFilters}>
              Clear all filters
            </Button>
          )}
        </Card>
      ) : (
        <div className={`space-y-2.5 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {grouped
            ? stories.map((s, i) => (
                <ArticleCard key={s.key} article={s.lead} story={s} index={i} defaultOpen={!!filters.cluster} />
              ))
            : articles.map((a, i) => <ArticleCard key={a.id} article={a} index={i} />)}
        </div>
      )}

      {count > 0 && <FeedPagination onNavigate={toTop} noun={grouped ? 'stories' : 'articles'} />}
    </section>
  )
}
