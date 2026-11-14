// Hash-based router for the landing, home, article and story views.
import { useEffect, useState } from 'react'
import { clearEntered, hasEntered, markEntered } from '@/lib/entry'

/** The views the app can show. */
export type Route = { name: 'landing' } | { name: 'home' } | { name: 'article'; id: number } | { name: 'story'; id: number }

/** Turn a URL hash into a route; first-time visitors with no hash land on the landing page. */
export function parseRoute(hash: string, entered: boolean): Route {
  // "#/article/<numeric id>"
  const article = hash.match(/^#\/article\/(\d+)$/)
  if (article) return { name: 'article', id: Number(article[1]) }
  // "#/story/<numeric cluster id>"
  const story = hash.match(/^#\/story\/(\d+)$/)
  if (story) return { name: 'story', id: Number(story[1]) }
  if (hash === '#/welcome') return { name: 'landing' }
  // The bare root shows the landing page until the visitor has entered once; any other hash goes home.
  return !entered && (hash === '' || hash === '#/') ? { name: 'landing' } : { name: 'home' }
}

/** Read the current route from the URL hash. */
function parse(): Route {
  return parseRoute(location.hash, hasEntered())
}

/** Hash routing keeps existing `/#/article/:id` links working with no server rewrite. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse)
  // Re-read the route whenever the hash changes (links, back/forward, or a manual nudge).
  useEffect(() => {
    /** Update the route from the new hash. */
    const on = () => setRoute(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

/** Leave the landing page for the dashboard and remember it, so the landing page is skipped next visit. */
export function enterDashboard() {
  markEntered()
  // Setting the same hash fires no event, so nudge the router by hand when already at "#/".
  if (location.hash === '#/') window.dispatchEvent(new HashChangeEvent('hashchange'))
  else location.hash = '#/'
  window.scrollTo({ top: 0 })
}

/** Leave the dashboard and show the landing page again, as when a demo visitor signs out. */
export function leaveDashboard() {
  clearEntered()
  location.hash = '#/welcome'
  window.scrollTo({ top: 0 })
}

/** Navigate to the home view and scroll to the top. */
export function goHome() {
  location.hash = '#/'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
