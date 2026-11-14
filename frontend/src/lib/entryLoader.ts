// Loader logic for the unprefixed routes, kept apart from the router so it can be unit-tested without a browser.
import { redirect } from 'react-router'
import type { SessionMode } from '@/lib/api'
import { legacyHashPath } from '@/lib/legacyHash'
import { prefixRedirect } from '@/lib/mode'

/** Redirect an unprefixed URL for legacy hash links, demo/workspace visitors and first-time visitors, or return null to render it. */
export function entryLoader(pathname: string, hash: string, entered: boolean, token: SessionMode): Response | null {
  const legacy = legacyHashPath(hash)
  if (legacy) return redirect(legacy)
  const prefixed = prefixRedirect(pathname, token)
  if (prefixed) return redirect(prefixed)
  return pathname === '/' && !entered ? redirect('/welcome') : null
}
