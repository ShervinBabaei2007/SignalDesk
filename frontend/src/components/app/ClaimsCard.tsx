// What the outlets agree and disagree on, claim by claim.
import { CheckCheck, Scale, User } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { Claim, Claims } from '@/lib/api'
import { cn } from '@/lib/utils'

/** Look of each claim status. */
const STATUS = {
  disputed: { label: 'Disputed', icon: Scale, tone: 'border-negative/40 bg-negative/8', text: 'text-negative' },
  agreed: { label: 'Agreed', icon: CheckCheck, tone: 'border-positive/30 bg-positive/6', text: 'text-positive' },
  single: { label: 'One outlet', icon: User, tone: 'bg-background/50', text: 'text-muted-foreground' },
} as const

/** One claim with the outlets behind it and, when disputed, each outlet's figure. */
function ClaimRow({ claim }: { claim: Claim }) {
  const s = STATUS[claim.status]
  const Icon = s.icon
  return (
    <li className={cn('space-y-1.5 rounded-lg border px-3 py-2.5', s.tone)}>
      <div className="flex items-start gap-2">
        <Icon className={cn('mt-0.5 size-4 shrink-0', s.text)} aria-hidden />
        <p className="text-sm leading-snug">{claim.text}</p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 pl-6">
        <span className={cn('text-[11px] font-semibold tracking-wide uppercase', s.text)}>{s.label}</span>
        {claim.status === 'disputed' && claim.values
          ? Object.entries(claim.values).map(([outlet, value]) => (
              <Badge key={outlet} variant="outline" className="h-5 gap-1 px-1.5 text-[11px] font-normal">
                <span className="font-semibold">{outlet}</span> {value}
              </Badge>
            ))
          : claim.outlets.map((outlet) => (
              <Badge key={outlet} variant="secondary" className="h-5 px-1.5 text-[11px] font-normal">
                {outlet}
              </Badge>
            ))}
      </div>
    </li>
  )
}

/** The claim-level comparison of a story: disputed claims first, then agreed, then single-source figures. */
export function ClaimsCard({ claims }: { claims: Claims }) {
  const disputed = claims.items.filter((c) => c.status === 'disputed').length
  return (
    <Card>
      <CardHeader className="gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-[15px]">Claim by claim</CardTitle>
          <Badge variant="outline" title={claims.kind === 'ai' ? 'Claims were extracted and judged by the configured model' : 'Claims were found by matching sentences across the reports'}>
            {claims.kind === 'ai' ? 'AI-assisted' : 'Extracted from the reports'}
          </Badge>
        </div>
        <CardDescription>
          {claims.items.length
            ? `${disputed ? `${disputed} disputed. ` : 'No conflicting figures found. '}Check the source reports before relying on any single claim.`
            : 'No claims that several outlets make were found yet. They appear as more outlets report on the story.'}
        </CardDescription>
      </CardHeader>
      {claims.items.length > 0 && (
        <CardContent>
          <ul className="space-y-2">
            {claims.items.map((c, i) => (
              <ClaimRow key={`${c.status}-${i}`} claim={c} />
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  )
}
