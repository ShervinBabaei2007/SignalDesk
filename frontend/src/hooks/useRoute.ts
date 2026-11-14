// Hash-based router for the landing, home, article and story views.
import { useEffect, useState } from 'react'
import { hasEntered, markEntered } from '@/lib/entry'

/** The views the app can show. */
export type Route = { name: 'landing' } | { name: 'home' } | { name: 'article'; id: number } | { name: 'story'; id: number }

/** Turn a URL hash into a route; first-time visitors with no hash land on the landing page. */
export function parseRoute(hash: string, entered: boolean): Route {
  const article = hash.match(/^#\/article\/(\d+)$/)
  if (article) return { name: 'article', id: Number(article[1]) }
  const story = hash.match(/^#\/story\/(\d+)$/)
  if (story) return { name: 'story', id: Number(story[1]) }
  if (hash === '#/welcome') return { name: 'landing' }
  return !entered && (hash === '' || hash === '#/') ? { name: 'landing' } : { name: 'home' }
}

/** Read the current route from the URL hash. */
function parse(): Route {
  return parseRoute(location.hash, hasEntered())
}

/** Hash routing keeps existing `/#/article/:id` links working with no server rewrite. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse)
  useEffect(() => {
    const on = () => setRoute(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

/** Leave the landing page for the dashboard and remember it, so the landing page is skipped next visit. */
export function enterDashboard() {
  markEntered()
  if (location.hash === '#/') window.dispatchEvent(new HashChangeEvent('hashchange')) // already there: nudge the router
  else location.hash = '#/'
  window.scrollTo({ top: 0 })
}

/** Navigate to the home view and scroll to the top. */
export function goHome() {
  location.hash = '#/'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
