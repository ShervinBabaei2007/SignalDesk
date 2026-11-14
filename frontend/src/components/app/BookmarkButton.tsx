// Button that saves or unsaves an article in the browser's library.
import { Bookmark } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useLibrary } from '@/hooks/useLibrary'
import { cn } from '@/lib/utils'

/** Save an article to read later. Stored in this browser; find it under Topics → Saved. */
export function BookmarkButton({ id, withLabel = false }: { id: number; withLabel?: boolean }) {
  const { isSaved, toggleSaved } = useLibrary()
  const saved = isSaved(id)
  const label = saved ? 'Remove from saved' : 'Save for later'
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant={withLabel ? 'outline' : 'ghost'}
            size={withLabel ? 'lg' : 'icon-sm'}
            aria-pressed={saved}
            aria-label={label}
            className={withLabel ? 'h-10' : undefined}
            onClick={(e) => {
              e.stopPropagation() // cards are clickable; saving must not open the article
              toggleSaved(id)
              toast(saved ? 'Removed from saved' : 'Saved for later')
            }}
          />
        }
      >
        <Bookmark className={cn(saved && 'fill-current text-link')} data-icon={withLabel ? 'inline-start' : undefined} />
        {withLabel && (saved ? 'Saved' : 'Save')}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}
