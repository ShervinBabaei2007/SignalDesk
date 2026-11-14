// Copy or download the daily brief as text, with a toast for the outcome (a workspace's way to share the brief).
import { toast } from 'sonner'
import type { Digest } from '@/lib/api'
import { briefFilename, digestText } from '@/lib/brief'

/** Toast that the brief cannot be shared yet, returning true when it is still loading. */
function stillLoading(digest: Digest | null): digest is null {
  if (!digest) toast.error('The brief is still loading')
  return !digest
}

/** Copy the brief to the clipboard. */
export async function copyBrief(digest: Digest | null) {
  if (stillLoading(digest)) return
  try {
    await navigator.clipboard.writeText(digestText(digest))
    toast.success('Daily brief copied')
  } catch {
    toast.error('Could not copy. Try the download instead')
  }
}

/** Save the brief as a .txt file. */
export function downloadBrief(digest: Digest | null) {
  if (stillLoading(digest)) return
  const url = URL.createObjectURL(new Blob([digestText(digest)], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = briefFilename(digest)
  link.click()
  URL.revokeObjectURL(url)
}
