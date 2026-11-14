// Imperative navigation for code that runs outside the router (toast actions) or on a button click.
import type { createBrowserRouter } from 'react-router'
import { clearEntered, markEntered } from '@/lib/entry'
import { modeFromPath, withBase, type Feature } from '@/lib/mode'
import { markStep } from '@/lib/onboarding'

type Router = ReturnType<typeof createBrowserRouter>

/** The app's router, registered once at startup by `router.tsx`. */
let router: Router | null = null

/** Window events that ask the header or welcome dialog to open something, since those dialogs live there. */
export const NAV_EVENTS = {
  openTool: 'signaldesk:open-tool',
  locked: 'signaldesk:locked',
  openWelcome: 'signaldesk:open-welcome',
} as const

/** Remember the router so non-component code can navigate. */
export function registerRouter(r: Router) {
  router = r
}

/** The current URL path, or "/" before the router exists. */
function here(): string {
  return router?.state.location.pathname ?? '/'
}

/** Go to an in-app path such as `/article/5`, staying inside the current mode (`/demo/...`, `/workspace/...`). */
export function navigateTo(path: string) {
  void router?.navigate(withBase(here(), path))
}

/** Go to an absolute path as given, for example to switch from the demo to `/workspace`. */
export function navigateAbsolute(path: string) {
  void router?.navigate(path)
}

/** Tick an onboarding step for the mode the visitor is in (does nothing when browsing or as the owner). */
export function completeStep(id: string) {
  const mode = modeFromPath(here())
  if (mode) markStep(mode, id)
}

/** The tool dialogs the header owns, which other parts of the page can ask it to open. */
export type Tool = 'feeds' | 'watchlist'

/** Ask the header to open a tool dialog (used by the checklist buttons). */
export function openTool(tool: Tool) {
  window.dispatchEvent(new CustomEvent(NAV_EVENTS.openTool, { detail: tool }))
}

/** Ask the welcome dialog to open again (the header's Help button). */
export function openWelcome() {
  window.dispatchEvent(new Event(NAV_EVENTS.openWelcome))
}

/** Leave the landing page for the dashboard and remember it, so the landing page is skipped next visit. */
export function enterDashboard() {
  markEntered()
  navigateAbsolute('/')
}

/** Leave the dashboard and show the landing page again, as when a demo visitor signs out. */
export function leaveDashboard() {
  clearEntered()
  navigateAbsolute('/welcome')
}

/** Ask the header to show the "needs a workspace" prompt for a locked feature. */
export function openLocked(feature: Feature) {
  window.dispatchEvent(new CustomEvent(NAV_EVENTS.locked, { detail: feature }))
}
