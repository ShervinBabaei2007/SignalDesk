// Prompt shown when the demo visitor clicks a locked feature.
import { Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useMode } from '@/hooks/useMode'
import { FEATURES, type Feature } from '@/lib/mode'
import { navigateAbsolute } from '@/lib/nav'

/** Small lock icon shown next to a button's label while its feature is locked. */
export function LockMark({ feature }: { feature: Feature }) {
  const { locked } = useMode()
  return locked(feature) ? <Lock className="size-3 opacity-60" aria-hidden /> : null
}

/** Explains a locked feature and offers to open a workspace, where it is unlocked. */
export function LockedDialog({ feature, onClose }: { feature: Feature | null; onClose: () => void }) {
  const info = feature ? FEATURES[feature] : null
  return (
    <Dialog open={feature !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="mb-1 grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
            <Lock className="size-5" aria-hidden />
          </div>
          <DialogTitle>{info?.headline}</DialogTitle>
          <DialogDescription>{info?.pitch}</DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          A workspace is free, needs no sign-up and is private to you. The demo stays exactly as it is.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Keep exploring the demo</Button>
          <Button onClick={() => { onClose(); navigateAbsolute('/workspace') }}>Open a workspace</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
