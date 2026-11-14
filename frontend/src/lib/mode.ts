// Which mode the visitor is in (from the URL prefix or token), what the demo locks, and the path helpers around both.
import type { SessionMode } from '@/lib/api'

/** The modes that own a URL prefix. */
export type PrefixMode = 'demo' | 'workspace'

/** The mode named by the first URL segment (`/demo/...`, `/workspace/...`), or null for unprefixed paths. */
export function modeFromPath(pathname: string): PrefixMode | null {
  const first = pathname.split('/')[1]
  return first === 'demo' || first === 'workspace' ? first : null
}

/** The URL prefix of the current mode: "/demo", "/workspace", or "" for browsing and the owner. */
export function basePath(pathname: string): '' | '/demo' | '/workspace' {
  const mode = modeFromPath(pathname)
  return mode ? `/${mode}` : ''
}

/** Put the current mode's prefix in front of an in-app path such as `/article/5`. */
export function withBase(pathname: string, to: string): string {
  const base = basePath(pathname)
  return to === '/' ? base || '/' : `${base}${to}`
}

/** The prefixed path an unprefixed URL should move to for a demo or workspace visitor, or null to stay put. */
export function prefixRedirect(pathname: string, token: SessionMode): string | null {
  if (token !== 'demo' && token !== 'workspace') return null
  return pathname === '/' ? `/${token}` : `/${token}${pathname}`
}

/** Features the demo shows but locks until the visitor opens a workspace. */
export type Feature = 'feeds' | 'watchlist' | 'brief' | 'export'

/** What each lockable feature is, in the words the locked prompt uses. */
export const FEATURES: Record<Feature, { title: string; headline: string; pitch: string }> = {
  feeds: {
    title: 'Your own feeds',
    headline: 'Adding your own feeds needs a workspace',
    pitch: 'Add any RSS feed and SignalDesk will cluster, score and summarise it. The demo uses a shared set of feeds.',
  },
  watchlist: {
    title: 'Watchlist and alerts',
    headline: 'Watchlist alerts need a workspace',
    pitch: 'Watch a term, like a company or a topic, and get an alert whenever enough outlets cover it.',
  },
  brief: {
    title: 'Copy and download the brief',
    headline: 'Copying the daily brief needs a workspace',
    pitch: 'Copy the daily brief as text, or download it, to share with your team.',
  },
  export: {
    title: 'CSV export',
    headline: 'CSV export needs a workspace',
    pitch: 'Export your articles with their sentiment and information scores for your own analysis.',
  },
}

/** True when this mode shows the feature but may not use it; only the demo is limited. */
export function isLocked(mode: SessionMode, feature: Feature): boolean {
  return mode === 'demo' && feature in FEATURES
}
