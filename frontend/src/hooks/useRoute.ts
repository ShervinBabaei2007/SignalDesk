// Hash-based router for the home, article and story views.
import { useEffect, useState } from 'react'

/** The views the app can show. */
export type Route = { name: 'home' } | { name: 'article'; id: number } | { name: 'story'; id: number }

/** Read the current route from the URL hash. */
function parse(): Route {
  const article = location.hash.match(/^#\/article\/(\d+)$/)
  if (article) return { name: 'article', id: Number(article[1]) }
  const story = location.hash.match(/^#\/story\/(\d+)$/)
  return story ? { name: 'story', id: Number(story[1]) } : { name: 'home' }
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

/** Navigate to the home view and scroll to the top. */
export function goHome() {
  location.hash = '#/'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
