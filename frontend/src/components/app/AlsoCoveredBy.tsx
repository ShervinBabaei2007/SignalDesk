// Lists the other outlets' reports of the same story under an article.
import { ArrowRight, ChevronRight, Layers } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { BlurFade } from '@/components/ui/blur-fade'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { InfoScore } from '@/components/app/InfoScore'
import { SentimentBadge } from '@/components/app/Sentiment'
import type { RelatedArticle } from '@/lib/api'
import { domainOf, sourceHue, timeAgo } from '@/lib/format'

/** Round avatar with the outlet's initial, coloured per outlet. */
export function SourceAvatar({ name, size = 'lg' }: { name: string; size?: 'default' | 'lg' }) {
  const hue = sourceHue(name)
  return (
    <Avatar size={size}>
      <AvatarFallback
        className="font-semibold"
        style={{ background: `hsl(${hue} 70% 45% / 0.18)`, color: `hsl(${hue} 80% 62%)` }}
      >
        {name.trim().charAt(0).toUpperCase()}
      </AvatarFallback>
    </Avatar>
  )
}

/** A link to one related report, with a hover card previewing its summary. */
function Row({ item, index }: { item: RelatedArticle; index: number }) {
  const snippet = item.summary_deep || item.summary
  const domain = domainOf(item.url)
  return (
    <BlurFade delay={0.05 * index} duration={0.3} offset={6}>
      <HoverCard>
        <HoverCardTrigger
          delay={250}
          render={
            <a
              href={`#/article/${item.id}`}
              className="group flex items-center gap-3 rounded-lg border bg-background/50 px-3 py-2.5 transition-colors hover:border-foreground/20 hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            />
          }
        >
          <SourceAvatar name={item.source} />
          <div className="min-w-0 flex-1">
            <div className="line-clamp-2 text-sm leading-snug font-medium">{item.title}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/80">{item.source}</span>
              <span>·</span>
              <span>{timeAgo(item.published_at)}</span>
            </div>
          </div>
          <InfoScore score={item.info_score} variant="bar" className="hidden sm:inline-flex" />
          <span className="hidden w-28 justify-end md:flex">
            <SentimentBadge score={item.sentiment} />
          </span>
          <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
        </HoverCardTrigger>
        <HoverCardContent className="w-80 space-y-2" align="start">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">{item.source}</span>
            {domain && <span>{domain}</span>}
          </div>
          <div className="text-sm leading-snug font-semibold">{item.title}</div>
          {snippet && <p className="line-clamp-4 text-[13px] leading-relaxed text-muted-foreground">{snippet}</p>}
          <div className="flex items-center justify-between pt-1">
            <SentimentBadge score={item.sentiment} />
            <span className="text-xs text-link">Open summary →</span>
          </div>
        </HoverCardContent>
      </HoverCard>
    </BlurFade>
  )
}

/** Card under an article listing other outlets' coverage of the same story. */
export function AlsoCoveredBy({ items, clusterId }: { items: RelatedArticle[]; clusterId?: number | null }) {
  if (!items.length) return null
  const outlets = new Set(items.map((i) => i.source)).size
  return (
    <Card className="gap-3 bg-muted/30 shadow-none">
      <CardHeader className="gap-1">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-[15px]">
            <Layers className="size-4 text-link" aria-hidden /> Also covered by
          </CardTitle>
          <Badge variant="secondary">{items.length} more {items.length === 1 ? 'report' : 'reports'}</Badge>
        </div>
        <CardDescription>
          The same story from {outlets} other {outlets === 1 ? 'outlet' : 'outlets'}, ranked by how much information each report carries.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((item, i) => (
          <Row key={item.id} item={item} index={i} />
        ))}
        {clusterId != null && (
          <a
            href={`#/story/${clusterId}`}
            className="inline-flex items-center gap-1 rounded-md px-1 py-1 text-sm font-medium text-link hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            See the full story: brief and outlet comparison <ArrowRight className="size-3.5" aria-hidden />
          </a>
        )}
      </CardContent>
    </Card>
  )
}
