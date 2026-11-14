// Onboarding state: the welcome dialog and "Get started" checklist, tracked separately for the demo and a workspace.
import { useSyncExternalStore } from 'react'
import type { PrefixMode } from '@/lib/mode'
import type { Tool } from '@/lib/nav'

/** One checklist item. */
export interface Step {
  id: string
  title: string
  hint: string
  /** The tool dialog the row's button opens. */
  action?: { label: string; tool: Tool }
}

/** The checklist for each mode: the demo is a guided read, a workspace is about setting things up. */
export const STEPS: Record<PrefixMode, Step[]> = {
  demo: [
    { id: 'story', title: 'Open a story', hint: 'A story groups reports from different outlets about one event.' },
    { id: 'article', title: 'Read an article', hint: 'See the summary, sentiment and information score.' },
    { id: 'filter', title: 'Filter the feed', hint: 'Pick a topic, sentiment or outlet in the filter bar.' },
    { id: 'ingest', title: 'Run a live ingest', hint: 'Use “Ingest feeds” at the top to fetch fresh articles.' },
  ],
  workspace: [
    { id: 'feed', title: 'Add a feed', hint: 'Paste an RSS URL for a site you follow.', action: { label: 'Add feed', tool: 'feeds' } },
    { id: 'ingest', title: 'Run your first ingest', hint: 'Use “Ingest feeds” to pull in articles from your feeds.' },
    { id: 'watch', title: 'Watch a term', hint: 'Get alerted when several outlets cover it.', action: { label: 'Add watch', tool: 'watchlist' } },
    { id: 'story', title: 'Open a story', hint: 'Compare how different outlets covered the same event.' },
    { id: 'save', title: 'Save an article', hint: 'Use the bookmark on any article to keep it.' },
  ],
}

/** Stored state for one mode. */
export interface OnboardingState {
  welcomed: boolean
  dismissed: boolean
  done: string[]
}

/** State for a mode with nothing stored. */
const EMPTY: OnboardingState = { welcomed: false, dismissed: false, done: [] }

/** localStorage key for a mode's onboarding state. */
function key(mode: PrefixMode): string {
  return `signaldesk-onboarding-${mode}`
}

/** Parse stored state, ignoring anything malformed. */
export function parseState(raw: string | null): OnboardingState {
  try {
    const v = JSON.parse(raw ?? '{}')
    return {
      welcomed: v.welcomed === true,
      dismissed: v.dismissed === true,
      done: Array.isArray(v.done) ? v.done.filter((x: unknown) => typeof x === 'string') : [],
    }
  } catch {
    return EMPTY
  }
}

/** How many of the mode's steps are done, and the total, ignoring unknown ids. */
export function progress(mode: PrefixMode, done: string[]): { done: number; total: number } {
  const ids = new Set(STEPS[mode].map((s) => s.id))
  return { done: new Set(done.filter((d) => ids.has(d))).size, total: ids.size }
}

// A tiny external store, so every component reading the state updates when any of them changes it.
const listeners = new Set<() => void>()
const cache = new Map<PrefixMode, { raw: string | null; state: OnboardingState }>()

/** Read a mode's state; the same object is returned until the stored text changes, as React requires. */
function read(mode: PrefixMode): OnboardingState {
  let raw: string | null
  try {
    raw = localStorage.getItem(key(mode))
  } catch {
    return cache.get(mode)?.state ?? EMPTY // storage unavailable: use the in-memory copy
  }
  const hit = cache.get(mode)
  if (hit && hit.raw === raw) return hit.state
  const state = parseState(raw)
  cache.set(mode, { raw, state })
  return state
}

/** Save a change to a mode's state and tell subscribers. */
function update(mode: PrefixMode, change: Partial<OnboardingState>) {
  const next = { ...read(mode), ...change }
  try {
    localStorage.setItem(key(mode), JSON.stringify(next))
  } catch {
    // Storage unavailable: keep the change in memory until reload.
    cache.set(mode, { raw: null, state: next })
  }
  listeners.forEach((l) => l())
}

/** Record that a step is done (no-op when it already is, or is not part of the mode's list). */
export function markStep(mode: PrefixMode, id: string) {
  const state = read(mode)
  if (state.done.includes(id) || !STEPS[mode].some((s) => s.id === id)) return
  update(mode, { done: [...state.done, id] })
}

/** Mark the welcome dialog as seen. */
export function setWelcomed(mode: PrefixMode) {
  update(mode, { welcomed: true })
}

/** Hide or bring back the checklist card. */
export function setDismissed(mode: PrefixMode, dismissed: boolean) {
  update(mode, { dismissed })
}

/** Register a listener for state changes and return its unsubscribe function. */
function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Subscribe to a mode's onboarding state. */
export function useOnboarding(mode: PrefixMode): OnboardingState {
  return useSyncExternalStore(subscribe, () => read(mode))
}
